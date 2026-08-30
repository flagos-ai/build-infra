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

"""Audit built wheels' declared dependencies against a critical package list.

The runtime image bakes a pinned matrix (torch / triton / flag_gems / …) and
app images install wheels single-step, so a wheel that *declares* one of
those packages gives pip a reason to resolve/upgrade it and silently drift
the matrix. This gate reads each wheel's METADATA ``Requires-Dist`` and fails
the build when a watched package is declared.

``--watch`` entries come in three forms:

* ``name`` — declare-and-fail: any Requires-Dist on the name fails the audit.
* ``name*`` — same, prefix match (``nvidia-*`` matches ``nvidia-cudnn-cu13``).
* ``name==version`` — version-aware: the runtime pins this exact version, so
  a declared constraint only fails when that pinned version does not satisfy
  it. A bare ``numpy`` (or ``numpy>=1.20,<2``) passes against
  ``numpy==1.26.4``; ``numpy>=2`` fails. Use this for packages the image pins
  deliberately (numpy is stack-pinned at 1.26.4, torch's C ABI floor) where a
  lower-bound declaration is a false floor rather than a real drift. A
  pinned-version FAIL is a special case: verify whether the package genuinely
  needs the higher version before touching the watchlist.

The watched set is product-line specific (vllm's critical list and sglang's
differ, e.g. numpy is critical for vllm but a legal sglang dependency), so
the script ships no default list — callers pass theirs with ``--watch``.

Usage:
    python3 audit-deps.py --watch pkg [--watch pkg ...] wheel.whl [...]
    python3 audit-deps.py --watch pkg [--watch pkg ...] --pkginfo PKG-INFO

Exit status: 0 = clean, 1 = a watched package is declared (or a pinned watch
entry's declared constraint is unsatisfiable).
"""

import argparse
import re
import sys
import zipfile

# PEP 508 distribution name: [A-Za-z0-9._-]+ — the name stops at the first
# '[', '<', '>', '=', '!', '~', '(', or space (extras / version / marker).
_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")
_OP_RE = re.compile(r"^(~=|===|==|!=|<=|>=|<|>)?\s*(.+)$")
_DIGIT_RE = re.compile(r"(\d+)")


def _requires_dist(lines: list[str]) -> list[tuple[str, str]]:
    """Extract (name, version-specifier) pairs from METADATA / PKG-INFO lines.

    A line is ``Requires-Dist: name[extras]>=spec; marker`` — drop the label,
    extras, and environment marker, leaving the name and its specifier string
    (``""`` when bare). Lines whose marker references ``extra`` (e.g.
    ``; extra == "test"``) are optional extras: installed only when that extra
    is explicitly requested, never by a plain single-step ``pip install``, so
    they cannot drift the runtime matrix and are skipped. python_version
    markers are not evaluated — consistent with the script's stance that any
    declaration is a candidate drift.
    """
    deps = []
    for ln in lines:
        if ln.startswith("Requires-Dist:"):
            body = ln.split(":", 1)[1]
            marker = body.split(";", 1)[1] if ";" in body else ""
            if re.search(r"\bextra\b", marker):
                continue  # optional extra — not installed by default
            m = _NAME_RE.match(body.lstrip())
            if not m:
                continue
            name = m.group(0)
            rest = body.lstrip()[m.end():].split(";", 1)[0].strip()
            if rest.startswith("["):  # drop [extras]
                rest = rest.split("]", 1)[1] if "]" in rest else ""
            deps.append((name, rest.strip()))
    return deps


def _wheel_metadata_lines(path: str) -> list[str]:
    """METADATA lines inside a wheel zip (or [] if none)."""
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith(".dist-info/METADATA"):
                return zf.read(name).decode().splitlines()
    return []


def _version_key(v: str) -> tuple[int, ...]:
    """Release version → comparable int tuple (``1.26.4`` → ``(1, 26, 4)``).

    PEP 440 in miniature, good enough for the release versions this gate
    compares (floors like ``>=1.20``, ceilings like ``<2``, ``==1.26.*``).
    Epochs, pre/post/dev labels and arbitrary ``===`` strings are out of
    scope; a segment without a leading digit counts as 0.
    """
    v = v.split("+", 1)[0]  # drop local version
    return tuple(
        int(m.group(1)) if (m := _DIGIT_RE.match(seg)) else 0
        for seg in v.split(".")
    )


def _pad(t: tuple[int, ...], n: int) -> tuple[int, ...]:
    return t + (0,) * max(0, n - len(t))


def _specifier_ok(spec: str, pinned: tuple[int, ...]) -> bool:
    """True when ``pinned`` satisfies a PEP 440-ish specifier string.

    ``spec`` is the raw version specifier from a Requires-Dist line, e.g.
    ``""`` (bare), ``>=1.20``, ``<2,>=1.20``, ``==1.26.*``, ``~=1.21``.
    An unparseable operator defaults to permissive (True) rather than
    inventing a failure.
    """
    if not spec:
        return True
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        m = _OP_RE.match(part)
        if not m:
            continue
        op, ver = m.groups()
        op = op or "=="
        ver = ver.strip()

        if ver.endswith(".*"):  # wildcard: only valid with == / !=
            prefix = _version_key(ver[:-2])
            head = _pad(pinned, len(prefix))[: len(prefix)]
            if op in ("==", "===") and head != prefix:
                return False
            if op == "!=" and head == prefix:
                return False
            continue

        key = _version_key(ver)
        if op == "~=":  # ~=1.26 → >=1.26,<1.27 ; ~=1.4.5 → >=1.4.5,<1.5
            upper = list(key[:-1]) if len(key) > 1 else [0]
            upper[-1] += 1
            n = max(len(pinned), len(key), len(upper))
            a = _pad(pinned, n)
            if not (a >= _pad(key, n) and a < _pad(tuple(upper), n)):
                return False
            continue

        n = max(len(pinned), len(key))
        a, b = _pad(pinned, n), _pad(key, n)
        if op in ("==", "==="):
            if a != b:
                return False
        elif op == "!=":
            if a == b:
                return False
        elif op == ">=":
            if a < b:
                return False
        elif op == "<=":
            if a > b:
                return False
        elif op == ">":
            if a <= b:
                return False
        elif op == "<":
            if a >= b:
                return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watch",
        action="append",
        metavar="PKG[==VERSION]",
        help="package to fail on if declared (repeatable). Forms: bare name "
             "(any declaration fails), name* (prefix match), name==version "
             "(fail only when the declared constraint is not satisfied by the "
             "runtime-pinned version). Required — no product default.",
    )
    parser.add_argument(
        "--pkginfo",
        metavar="FILE",
        help="audit a PEP 566 metadata text file (an sdist's PKG-INFO) "
             "instead of wheels — the same Requires-Dist gate for source "
             "tarballs (build-sdist.sh)",
    )
    parser.add_argument("wheels", nargs="*", metavar="wheel.whl")
    args = parser.parse_args()

    if not args.watch:
        parser.error("at least one --watch is required — the script ships "
                     "no product-specific default list")
    if args.pkginfo and args.wheels:
        parser.error("give either --pkginfo or wheel paths, not both")
    if not args.pkginfo and not args.wheels:
        parser.error("no input: pass at least one wheel.whl, or --pkginfo FILE")

    declare_fail: set[str] = set()  # bare names: any declaration fails
    prefixes: set[str] = set()      # name* entries
    pinned: dict[str, tuple[str, tuple[int, ...]]] = {}  # name → (ver, key)
    for w in args.watch:
        wl = w.lower().replace("_", "-")
        if "==" in wl:
            name, ver = wl.split("==", 1)
            if not _NAME_RE.fullmatch(name) or not ver or "*" in ver:
                parser.error(f"--watch {w}: pinned form must be "
                             "name==version (concrete version, no wildcard)")
            pinned[name] = (ver, _version_key(ver))
        elif wl.endswith("*"):
            prefixes.add(wl[:-1])
        elif re.search(r"[<>=!~]", wl):
            parser.error(f"--watch {w}: only bare name, name*, or "
                         "name==version are supported")
        else:
            declare_fail.add(wl)

    failed = False
    artifacts = [args.pkginfo] if args.pkginfo else args.wheels
    for artifact in artifacts:
        lines = (open(artifact) if args.pkginfo
                 else _wheel_metadata_lines(artifact))
        deps = _requires_dist(lines)
        declared: dict[str, list[str]] = {}
        for name, spec in deps:
            declared.setdefault(name, []).append(spec)

        hits = []  # (display, pinned_violation: bool)
        for name in sorted(declared):
            specs = declared[name]
            if name in declare_fail:
                hits.append((name, False))
            elif name in pinned:
                ver, key = pinned[name]
                bad = [s for s in specs if not _specifier_ok(s, key)]
                if bad:
                    hits.append((
                        f"{name} (declares {', '.join(bad)} — runtime-pinned "
                        f"{name}=={ver} does not satisfy it)", True))
            elif any(name.startswith(p) for p in prefixes):
                hits.append((name, False))

        print(f"{artifact}: requires {len(deps)} packages "
              f"(watchlist hits: {', '.join(h for h, _ in hits) if hits else 'none'})")
        if hits:
            failed = True
            for hit, pinned_violation in hits:
                if pinned_violation:
                    print(
                        f"  FAIL: {hit} — handle this case separately: either "
                        "the package genuinely needs the higher version (then "
                        "the runtime matrix must move) or its floor is a false "
                        "claim (then strip it in the repack).",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"  FAIL: declares critical package {hit} — "
                        "an app-image single-step install would drift the "
                        "runtime matrix. Drop it from the wheel's "
                        "dependencies; the image provides it.",
                        file=sys.stderr,
                    )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
