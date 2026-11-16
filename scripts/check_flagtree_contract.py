#!/usr/bin/env python3

# Copyright 2026 FlagOS Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Detect drift between FlagTree's build-time cache and what our builders stage.

Every backend's prebuilt inputs (LLVM trees, plugins, vendor runtime blobs) are
declared upstream in `python/setup_tools/utils/<backend>.py` as `cache.store()`
calls, and we stage a copy of each into the backend's builder image so the wheel
build never has to reach the network. That staging list is transcribed by hand,
one tarball name per `ARG ..._TARBALL`, and nothing compared it against upstream
until this script.

The reason it has to be a check rather than a habit: FlagTree resolves a cache
entry by NAME, and `setup_helper.check_file()` reports a hit on any existing path
without comparing a version. So an upstream bump that keeps the key stable is
adopted silently -- the wheel keeps building, stays green, and ships the older
LLVM. A bump that moves the key is the opposite: our staged copy is not found,
FlagTree falls through to its own download, and on a runner whose proxy cannot
reach ks3/bcebos the build dies with `The download failed, probably due to
network problems!` -- a network error whose cause is a version skew. Two daily
rows (kunlunxin, sunrise) failed exactly that way for days before this existed.

So each upstream store is classified against what the Containerfile stages:

  OK        a staged tarball is that store -- the same name, or the same
            package carrying the revision upstream pins
  STALE     the package is staged at a different revision -- fatal, and the
            silent case when the cache key stayed put
  MISSING   upstream declares it and we stage nothing resembling it -- fatal
  UNKNOWN   upstream pins a `version=` marker with no counterpart staged at
            all; informational, so the gap is visible rather than assumed clean
  LLVM-HASH the hash a `LLVM_SYSPATH` row stages is not the one its ref names
  HOOK      `register_cache()`'s signature moved, which is the change class no
            tarball name would ever show

The `LLVM-HASH` case is the `nvidia` / `amd` / `ppu` shape: they hand FlagTree a
path instead of a cache entry, so a stale builder image would keep serving the
previous tree with no name to compare at all.

The ref compared against is the one the row will actually build: its `daily.ref`
when it has an enabled daily row, otherwise the Containerfile's own
`FLAGTREE_VERSION` / `FLAGTREE_REF` default (a release tag). Rows with no
enabled daily are skipped unless named: the daily never touches their stage, so
a mismatch there is not drift that run would fix.

Usage:
  python3 scripts/check_flagtree_contract.py
  python3 scripts/check_flagtree_contract.py --rows iluvatar kunlunxin
  python3 scripts/check_flagtree_contract.py --upstream-dir /path/to/flagtree

Exit status 1 when any row is STALE, MISSING, LLVM-HASH or HOOK.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://raw.githubusercontent.com/flagos-ai/flagtree"
CACHE = Path(os.environ.get("FLAGTREE_CONTRACT_CACHE", "~/.cache/flagtree-contract")).expanduser()

# A store() whose `condition` names a backend we do not build (spacemit, thrive,
# rpu, tileir, cambricon) is not drift, so the table is driven by our rows.
STORE = "store"
SKIP_KWARGS = {"condition", "pre_hook", "post_hook"}
# A single token that is only a revision: a date (`20260403`), a dotted release
# (`0.7.1`), either with a `v`, or an all-hex build fingerprint (`f6ded0be`,
# `188a510`, `b0ca808`). Everything else in a tarball name is package identity.
_REVISION = re.compile(r"v?(?:[0-9a-f]+|\d+(?:\.\d+)+)(?:\.[a-z0-9]+)*")


# --------------------------------------------------------------------------
# upstream side
# --------------------------------------------------------------------------

def _http_get(url: str) -> str | None:
    """The URL's body, None on 404.

    curl, with the retries a flaky international link needs: the read has been
    seen to stall part-way through a 50 KB file and then succeed on a second
    attempt. Not `--fail`: the status is read from `--write-out` instead, so a
    404 stays distinguishable from a transport error -- a backend with no module
    of its own is normal, and that is the one status this check acts on.
    """
    out = subprocess.run(
        ["curl", "--silent", "--show-error", "--location",
         "--retry", "5", "--retry-delay", "3", "--retry-connrefused",
         "--connect-timeout", "20", "--max-time", "120",
         "--write-out", "\n%{http_code}", url],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"fetching {url}: {out.stderr.strip()}")
    body, _, code = out.stdout.rpartition("\n")
    if code == "404":
        return None
    if code != "200":
        raise SystemExit(f"fetching {url}: HTTP {code}")
    return body


def fetch(ref: str, path: str, upstream_dir: Path | None, offline: bool) -> str | None:
    """The file's text at `ref`, or None when it does not exist there."""
    if upstream_dir is not None:
        p = upstream_dir / path
        return p.read_text(encoding="utf-8") if p.is_file() else None

    cached = CACHE / ref / path
    if cached.is_file():
        return cached.read_text(encoding="utf-8")
    if offline:
        raise SystemExit(f"offline and {ref}/{path} is not in {CACHE}")

    text = _http_get(f"{UPSTREAM}/{ref}/{path}")
    if text is None:
        return None
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


def _consts(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"` strings, which the f-string URLs use."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out[t.id] = node.value.value
    return out


def _resolve(node: ast.AST, consts: dict[str, str]) -> str | None:
    """A URL/file kwarg as text: a literal, or an f-string over module constants."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name):
                if v.value.id not in consts:
                    return None
                parts.append(consts[v.value.id])
            else:
                return None
        return "".join(parts)
    return None


def stores(text: str) -> list[dict]:
    """Every cache.store() call in a backend module, with its kwargs resolved."""
    tree = ast.parse(text)
    consts = _consts(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == STORE):
            continue
        call = {}
        for kw in node.keywords:
            if kw.arg in SKIP_KWARGS:
                continue
            if kw.arg in ("file", "url", "version", "md5_digest", "copy_dst_path"):
                value = _resolve(kw.value, consts)
                # `files=(...)` and computed paths are copies out of an already
                # staged tree, not a download of their own.
                call[kw.arg] = value
        if call.get("url"):
            out.append(call)
    return out


# --------------------------------------------------------------------------
# our side
# --------------------------------------------------------------------------

def _staged_names(containerfile: Path) -> set[str]:
    """Tarball names this Containerfile downloads (ARG defaults + literals).

    Comments are dropped first: several of these files name a tarball in prose
    (the mthreads one lists both revisions it serves), and counting those would
    let a stale pin pass as staged.
    """
    text = containerfile.read_text(encoding="utf-8")
    code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())

    args: dict[str, str] = {}
    for m in re.finditer(r"^ARG\s+([A-Z0-9_]+)=(.*)$", code, re.M):
        args[m.group(1)] = m.group(2).strip()

    def expand(value: str, seen=()) -> str:
        def sub(m: re.Match) -> str:
            name = m.group(1) or m.group(2)
            if name in seen or name not in args:
                return m.group(0)
            return expand(args[name], seen + (name,))
        return re.sub(r"\$\{([A-Z0-9_]+)\}|\$([A-Z0-9_]+)", sub, value)

    names = set()
    for m in re.finditer(r"[A-Za-z0-9_.+-]+\.tar\.(?:gz|xz|bz2)", code):
        names.add(m.group(0))
    for value in args.values():
        expanded = expand(value)
        if re.search(r"\.tar\.(?:gz|xz|bz2)$", expanded):
            names.add(expanded)
    return names


def _declared_hash(containerfile: Path) -> str | None:
    """`ARG LLVM_HASH=` for the LLVM_SYSPATH rows, expanded."""
    text = containerfile.read_text(encoding="utf-8")
    m = re.search(r"^ARG\s+LLVM_HASH=([0-9a-f]+)", text, re.M)
    return m.group(1) if m else None


def _backend_of(containerfile: Path) -> tuple[str | None, str | None]:
    """(FLAGTREE_BACKEND, its FLAGTREE_VERSION/REF default) as literals."""
    text = containerfile.read_text(encoding="utf-8")
    backend = None
    m = re.search(r"FLAGTREE_BACKEND=([A-Za-z0-9_]+)", text)
    if m:
        backend = m.group(1)
    ref = None
    m = re.search(r"^ARG\s+FLAGTREE_(?:VERSION|REF)=(\S+)", text, re.M)
    if m:
        ref = m.group(1)
    return backend, ref


# --------------------------------------------------------------------------
# comparison
# --------------------------------------------------------------------------

def _family(name: str) -> str:
    """The package a tarball name belongs to, with its revision erased.

    Upstream moves a package by editing a version token in the name
    (`_v0.6.1` -> `_v0.7.0`), by swapping an LLVM commit (`llvm-71bd243f-` ->
    `llvm-ff67ef55-`), or by both. Tokens are compared, not the string: a token
    that is nothing but a revision fingerprint -- an all-hex run (a commit, a
    vendor build id) or a `v`-prefixed or dotted number (a release) -- is
    dropped, and the rest of the name is what identifies the package.

    What survives is exactly what makes two trees *different* packages rather
    than two versions of one: `llvm19` against `llvm22`, `llvm-pub22`, `printf`,
    `ubuntu2004`, `x86`. Dropping those would report a stale pin for a tree that
    is simply another tree.
    """
    s = re.sub(r"\.tar\.(?:gz|xz|bz2)$", "", name.lower())
    tokens = re.split(r"[^a-z0-9]+", s)
    keep = []
    for t in tokens:
        if not t:
            continue
        if _REVISION.fullmatch(t):
            continue
        keep.append(t)
    return "".join(keep)


def classify(declared: dict, staged: set[str]) -> tuple[str, str]:
    """(verdict, detail) for one upstream store against the staged name set.

    Upstream pins a revision two ways, and both have to count as a match:

    * in the name -- `iluvatar-llvm22-x86_64_v0.7.0.tar.gz`;
    * in a `version=` marker, with a stable name -- xpu's two LLVM 19 packages
      are *both* `xtdk-llvm19-ubuntu2004_x86_64.tar.gz` and are told apart only
      by their dated URL paths and markers. Our mirror renames those to carry
      the date (`_v20260916`), which is what makes them addressable at all, so
      comparing basenames alone would call both stale whatever we staged.

    A pinned version that appears in exactly one staged name is therefore a
    match, and one that appears in none is the stale case worth failing on.
    """
    name = declared["url"].rsplit("/", 1)[-1]
    if name in staged:
        return "OK", name

    version = (declared.get("version") or "").lstrip("v")
    if version:
        carrying = sorted(n for n in staged if version in n)
        if len(carrying) == 1:
            return "OK", f"{name} (staged {carrying[0]}, version={declared['version']})"
        if carrying:
            return "STALE", f"{name} version={declared['version']} matches {len(carrying)} staged tarballs"

    same = sorted(n for n in staged if _family(n) == _family(name))
    if same:
        pinned = f" version={declared['version']}" if version else ""
        return "STALE", f"{name}{pinned} (staged {', '.join(same)})"
    if version:
        return "UNKNOWN", f"{name} (upstream pins version={declared['version']}; no counterpart staged)"
    return "MISSING", name


def check_row(row: str, cfg: dict, upstream_dir: Path | None, offline: bool) -> list[tuple]:
    """Every finding for one backends.yaml row."""
    containerfile = ROOT / "packaging" / "flagtree" / cfg["containerfile"]
    daily = cfg.get("daily") or {}
    backend, literal_ref = _backend_of(containerfile)
    ref = daily.get("ref") if daily.get("enabled") else literal_ref
    ref = ref or daily.get("ref") or "main"

    findings = []

    # The LLVM_SYSPATH shape: the hash we stage has to be the one this ref names.
    declared_hash = _declared_hash(containerfile)
    if declared_hash:
        text = fetch(ref, "cmake/llvm-hash.txt", upstream_dir, offline)
        if text is not None:
            want = text.strip()[: len(declared_hash)]
            verdict = "OK" if want == declared_hash else "LLVM-HASH"
            findings.append((row, verdict, ref, f"staged {declared_hash}, {ref} names {want}"))

    if not backend:
        return findings

    text = fetch(ref, f"python/setup_tools/utils/{backend}.py", upstream_dir, offline)
    staged = _staged_names(containerfile)
    if text is None:
        # No module means no cache stores of its own (amd, nvidia, ppu run on
        # LLVM_SYSPATH or the default backend's helper).
        return findings

    # The hook signature our Containerfiles' staged layout is built around: a
    # refactor of it is the change class no tarball name would ever show.
    m = re.search(r"def register_cache\(([^)]*)\)", text)
    if m:
        params = [p.split("=")[0].strip() for p in m.group(1).split(",") if p.strip()]
        if params != ["cache", "flagtree_backend", "check_env", "set_llvm_env"]:
            findings.append((row, "HOOK", ref, f"register_cache({', '.join(params)})"))

    for declared in stores(text):
        verdict, detail = classify(declared, staged)
        findings.append((row, verdict, ref, detail))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rows", nargs="*", help="backend keys (default: the daily-enabled rows)")
    ap.add_argument("--upstream-dir", type=Path, help="read upstream from a local checkout")
    ap.add_argument("--offline", action="store_true", help="fail rather than fetch")
    ap.add_argument("--refresh", action="store_true", help="ignore the fetch cache")
    ap.add_argument("--quiet", action="store_true", help="only the failures")
    args = ap.parse_args()
    if args.refresh:
        # A cached copy is what the daily run must never read: the point is what
        # upstream changed since yesterday.
        shutil.rmtree(CACHE, ignore_errors=True)

    backends = yaml.safe_load(
        (ROOT / "packaging" / "flagtree" / "backends.yaml").read_text(encoding="utf-8")
    )["backends"]
    rows = args.rows or [r for r, cfg in backends.items() if (cfg.get("daily") or {}).get("enabled")]
    unknown = [r for r in rows if r not in backends]
    if unknown:
        raise SystemExit(f"unknown backend(s): {' '.join(unknown)}")

    findings = []
    for row in rows:
        findings.extend(check_row(row, backends[row], args.upstream_dir, args.offline))

    fatal = [f for f in findings if f[1] in ("STALE", "MISSING", "LLVM-HASH", "HOOK")]
    informational = [f for f in findings if f[1] == "UNKNOWN"]

    shown = fatal if args.quiet else findings
    for row, verdict, ref, detail in shown:
        print(f"{verdict:<9} {row:<18} {ref:<12} {detail}")

    if informational and not args.quiet:
        print(f"\n{len(informational)} store(s) pin a version marker the staged name cannot be "
              f"compared against; check by hand when the URL path moves.")

    if fatal:
        print(f"\n{len(fatal)} drift(s): republish the row's builder stage "
              f"(flagtree-builder.yml) after updating its Containerfile.", file=sys.stderr)
        return 1
    print(f"\nno drift across {len(rows)} row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
