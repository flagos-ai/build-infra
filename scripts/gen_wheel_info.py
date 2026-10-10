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

"""Record wheel publish events into ``packaging/wheel-info.yaml``.

``packaging/wheel-info.yaml`` is the wheel package catalog, and it is its own
record of what was published: each version row's ``pypi_index`` / ``python`` /
``os`` / ``arch`` are the union of the publish events that produced it. The
human copy — package order, ``short_name``, and the per-version ``desc_zh`` /
``desc_en`` / ``notes`` — is hand-written, edited in place.

So the publish step of every wheel workflow (the single source of truth for what
exists) appends one line to a manifest, and ``record`` merges those lines into
the catalog: only the four machine fields of the matching ``(name, version)``
row are touched, so the hand-written descriptions around them survive. A version
published twice from the same lane merges into the row already there rather than
duplicating it, which is what makes a re-run of a publish a no-op — no commit,
no PR. A version nobody has described yet gets a stub row and a printed note,
so the record PR shows a reviewer what still needs writing.

Events only, never full revalidation: a row is the union of the events that
produced it, and an event that was later superseded is kept.

The file is written back through the YAML dumper, so its layout (key order, list
indentation) is the dumper's and a comment written inside it does not survive a
record. Hand-written field *values* do.

Usage::

    python3 scripts/gen_wheel_info.py record --manifest .wheel-info/manifest.tsv \\
        --workflow flagcx [--dry-run]
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

CATALOG = REPO_ROOT / "packaging" / "wheel-info.yaml"

# A compiled wheel's filename carries the interpreter tag and the platform
# tag; a pure-Python wheel is py3-none-any. ``version`` here is the wheel's
# own version string — the catalog version may differ (e.g. megatron-core
# wheel filenames carry a +fl.<date>.g<sha> local segment while the catalog
# rows are +<mlf-branch>), so a manifest line only takes the version from the
# filename when it left its own column empty.
_WHEEL_RE = re.compile(
    r"^(?P<pkg>[^-]+)-(?P<version>[^-]+)-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^/]+)\.whl$"
)

# Platform tag → (os, arch). Compiled wheels are linux; any is the pure wheel.
_OS_ARCH = {
    "linux_x86_64": ("linux", "linux_x86_64"),
    "linux_aarch64": ("linux", "linux_aarch64"),
    "any": ("any", "any"),
}

# Canonical sort orders for the machine lists: python tags oldest to newest with
# py3 last, the two linux arch tags before any, and the hosted lane leading a
# multi-lane index list. Fixed orders (not alphabetical) so a render is
# deterministic whichever order events arrived in.
_PY_SORT = {"cp310": 0, "cp311": 1, "cp312": 2, "cp313": 3, "py3": 99}
_ARCH_SORT = {"linux_x86_64": 0, "linux_aarch64": 1, "any": 99}

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "flagos-ci",
    "GIT_AUTHOR_EMAIL": "noreply@flagos.net",
    "GIT_COMMITTER_NAME": "flagos-ci",
    "GIT_COMMITTER_EMAIL": "noreply@flagos.net",
}

# A version row's key order. A row created here has to match what a hand-written
# one looks like, or the merge would silently reformat the file around it.
_ROW_KEYS = ("version", "pypi_index", "desc_zh", "desc_en", "notes",
             "python", "os", "arch")
_MACHINE_FIELDS = ("pypi_index", "python", "os", "arch")


# ── git / GitHub helpers (mirror scripts/record_app_image_tag.py) ───────────


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args), check=check, capture_output=True, text=True, cwd=REPO_ROOT
    )


def _gh_api(method: str, path: str, body: dict | None = None) -> dict:
    """Call the GitHub REST API with GITHUB_TOKEN (no gh CLI dependency)."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Error: GH_TOKEN/GITHUB_TOKEN not set — cannot open a PR")
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ── manifest → catalog merge ────────────────────────────────────────────────


def _parse_wheel(filename: str) -> tuple[str, str, str] | None:
    """Return (version, python_tag, arch) from a wheel filename, or None."""
    m = _WHEEL_RE.match(filename)
    if not m:
        return None
    plat = m.group("plat")
    if plat not in _OS_ARCH:
        return None
    return m.group("version"), m.group("py"), _OS_ARCH[plat][1]


def _manifest_rows(manifest: Path) -> list[tuple[str, str, str, str]]:
    """[(pkg, version, index, filename)] from the manifest.

    ``pkg`` is the catalog package name, which the filename cannot be trusted to
    spell (vllm_plugin_fl builds ``vllm-plugin-fl``), so the hook states it.
    """
    rows = []
    for line in manifest.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            sys.exit(f"Error: manifest line must have 4 tab-separated fields: {line!r}")
        pkg, version, index, filename = parts
        if not version:
            parsed = _parse_wheel(filename)
            if not parsed:
                sys.exit(f"Error: cannot derive version from wheel filename: {filename}")
            version = parsed[0]
        rows.append((pkg, version, index, filename))
    return rows


def _canonical_indexes(indexes) -> str | list[str]:
    """One lane renders as a plain string, several as a leading-hosted list."""
    out = sorted(set(indexes), key=lambda i: (i != "flagos-pypi-hosted", i))
    return out[0] if len(out) == 1 else out


def _as_list(value) -> list[str]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _merge_event(row: dict, index: str, py: str, arch: str) -> bool:
    """Union one publish event's machine facts into a version row; True if changed.

    Unchanged means the event was already recorded — that is the whole
    idempotency story, so it has to be answered by comparing the row, not by
    remembering the event somewhere else.
    """
    indexes = _as_list(row.get("pypi_index")) + [index]
    if py == "py3":
        # A pure wheel is py3-none-any, and a row describes one kind of wheel.
        # An event that changes the row's kind replaces its machine lists rather
        # than merging into them: `py3` beside `cp312`, or `any` beside
        # `linux_x86_64`, would describe a wheel that cannot exist.
        pys, oss, archs = ["py3"], ["any"], ["any"]
    else:
        if _as_list(row.get("python")) == ["py3"]:
            pys, oss, archs = [], [], []
        else:
            pys = _as_list(row.get("python"))
            oss = _as_list(row.get("os"))
            archs = _as_list(row.get("arch"))
        if py not in pys:
            pys.append(py)
        if arch not in archs:
            archs.append(arch)
        os_ = _OS_ARCH.get(arch, ("linux", arch))[0]
        if os_ not in oss:
            oss.append(os_)

    new = {
        "pypi_index": _canonical_indexes(indexes),
        "python": sorted(pys, key=lambda p: _PY_SORT.get(p, 99)),
        "os": sorted(oss),
        "arch": sorted(archs, key=lambda a: _ARCH_SORT.get(a, 99)),
    }
    changed = False
    for field, value in new.items():
        if row.get(field) != value:
            row[field] = value
            changed = True
    return changed


def _find_package(data: dict, pkg: str) -> dict | None:
    for p in data.get("wheels", []):
        if p.get("name") == pkg:
            return p
    return None


def _find_version(pkg_block: dict, version: str) -> dict | None:
    for v in pkg_block.get("versions", []):
        if v.get("version") == version:
            return v
    return None


def _new_row(version: str) -> dict:
    row = {k: None for k in _ROW_KEYS}
    row["version"] = version
    for k in ("desc_zh", "desc_en", "notes"):
        row[k] = ""
    for k in ("python", "os", "arch"):
        row[k] = []
    return row


def _apply_manifest(data: dict, manifest: Path) -> tuple[int, list[str]]:
    """Merge every manifest line into the catalog; return (changed rows, notes)."""
    changed = 0
    notes = []
    for pkg, version, index, filename in _manifest_rows(manifest):
        parsed = _parse_wheel(filename)
        if not parsed:
            sys.exit(f"Error: cannot parse wheel filename: {filename}")
        _version, py, arch = parsed

        pkg_block = _find_package(data, pkg)
        if pkg_block is None:
            # A package nobody has described yet. Its short_name and descriptions
            # are stubs so the row is visible in the record PR, where the review
            # catches them before merge — render never invents human copy.
            pkg_block = {"name": pkg, "short_name": pkg, "versions": []}
            data.setdefault("wheels", []).append(pkg_block)
            notes.append(f"new package `{pkg}`: fill in short_name, desc_zh, desc_en")
        row = _find_version(pkg_block, version)
        if row is None:
            row = _new_row(version)
            pkg_block.setdefault("versions", []).append(row)
            notes.append(f"new version `{pkg} {version}`: fill in desc_zh, desc_en")
        if _merge_event(row, index, py, arch):
            changed += 1
    return changed, notes


def _dump(data: dict) -> str:
    return yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, default_flow_style=False
    )


# ── subcommands ─────────────────────────────────────────────────────────────


def cmd_record(args: argparse.Namespace) -> None:
    """Merge the manifest into the catalog → commit as flagos-ci → PR."""
    manifest = Path(args.manifest)
    if not manifest.is_file():
        sys.exit(f"Error: manifest not found: {manifest}")
    if not CATALOG.is_file():
        sys.exit(f"Error: {CATALOG} not found — nothing to merge into")

    data = yaml.safe_load(CATALOG.read_text()) or {}
    changed, notes = _apply_manifest(data, manifest)
    for note in notes:
        print(f"note: {note}")
    if not changed:
        print("every manifest line is already in the catalog — nothing to do")
        return
    text = _dump(data)

    if args.dry_run:
        # Nothing has been written yet, so a dry run only has to not write.
        old = CATALOG.read_text().splitlines()
        new = text.splitlines()
        sys.stdout.writelines(
            line + "\n" for line in difflib.unified_diff(
                old, new, "packaging/wheel-info.yaml", "packaging/wheel-info.yaml",
                lineterm="", n=2,
            )
        )
        print(f"[dry-run] {changed} row(s) would change — nothing written, no PR")
        return

    CATALOG.write_text(text)
    print(f"{changed} row(s) updated in {CATALOG}")

    workflow = args.workflow or "wheel"
    branch = f"auto/wheel-info-{workflow}"
    commit_msg = f"docs(wheel-info): record {workflow} wheel publish"
    _git("add", "packaging/wheel-info.yaml", check=False)
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("no wheel-info changes after recording — nothing to PR")
        return

    for k, v in GIT_IDENTITY.items():
        os.environ.setdefault(k, v)
    _git("config", "user.name", "flagos-ci", check=False)
    _git("config", "user.email", "noreply@flagos.net", check=False)
    _git("checkout", "-B", branch, check=False)
    _git("commit", "-m", commit_msg)

    probe = _git("ls-remote", "origin", f"refs/heads/{branch}", check=False)
    if probe.returncode == 0 and probe.stdout.strip():
        # Same record already on the branch (re-run / recovery): rebase onto it
        # and plain-push — we are its descendant, and --force would clobber it.
        _git("fetch", "origin", branch, check=False)
        if _git("rebase", f"origin/{branch}", check=False).returncode != 0:
            _git("rebase", "--abort", check=False)
            sys.exit(
                f"Error: {branch} already carries a wheel-info record — merge or close its "
                f"PR, then re-run the workflow"
            )
        _git("push", "origin", branch)
    else:
        # Branch deleted: recreate from fresh main so the record carries every
        # catalog change merged since this run was dispatched.
        _git("fetch", "origin", "main", check=False)
        if _git("rebase", "origin/main", check=False).returncode != 0:
            _git("rebase", "--abort", check=False)
            sys.exit(
                f"Error: {branch} conflicts with origin/main — re-run the workflow to record"
            )
        _git("push", "origin", branch)

    base = args.base or os.environ.get("GITHUB_REF_NAME", "main")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        sys.exit("Error: GITHUB_REPOSITORY not set — cannot open a PR")
    existing = _gh_api(
        "GET", f"/repos/{repo}/pulls?head={repo.split('/', 1)[0]}:{branch}&state=open"
    )
    if existing:
        print(f"PR already open for {branch}; updated content pushed")
        return
    body = (
        f"The `{workflow}` wheel workflow published wheels to the vendor PyPI and recorded "
        "the publish events into the matching rows of `packaging/wheel-info.yaml` "
        "(`pypi_index` / `python` / `os` / `arch` only — the hand-written descriptions are "
        "left as they are). No functional changes; the publish step keeps the catalog "
        "current from now on — see scripts/gen_wheel_info.py.\n\n"
        "This PR was written in part with the assistance of generative AI."
    )
    _gh_api("POST", f"/repos/{repo}/pulls", {
        "title": commit_msg,
        "head": branch,
        "base": base,
        "body": body,
    })


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record wheel publish events into the wheel package catalog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subs = parser.add_subparsers(dest="command", required=True)

    rp = subs.add_parser("record", help="Merge the manifest into the catalog, commit, open a PR")
    rp.add_argument("--manifest", required=True, help="path to the manifest TSV")
    rp.add_argument("--workflow", default="", help="workflow name → branch auto/wheel-info-<workflow>")
    rp.add_argument("--base", default="", help="PR base ref (default GITHUB_REF_NAME or main)")
    rp.add_argument("--dry-run", action="store_true", help="print the would-be diff; write nothing")
    rp.set_defaults(func=cmd_record)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
