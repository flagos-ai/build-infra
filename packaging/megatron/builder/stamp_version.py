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

"""Stamp the wheel version into Megatron-LM-FL's package_info.py.

Reads MLF_VERSION from the environment (e.g. "0.17.1.post20260812"), parses it
as MAJOR.MINOR.PATCH[<pre-release>] and rewrites the four static constants in
``megatron/core/package_info.py``. Blank MLF_VERSION derives commit-level
provenance from the git checkout instead:

  <repo public version>+fl.<commit-date>.g<short-sha>
    e.g. 0.17.1+fl.20260814.gba22f6b673f3

The public part stays the upstream megatron-core version (``==0.17.1`` pins
keep resolving — PEP 440 ignores local labels in == matching). The local label
carries two things: the committer date as a pure-numeric leading segment
(``20260814`` — PEP 440 compares numeric segments numerically, so two wheels
sort by build date and a human can see which is newer at a glance), and the
exact flagos-ai/Megatron-LM-FL commit cloned into the build
(``git clone --depth 1``) as the ``fl.g<sha>`` tail — so the wheel answers
"which MLF code is this?" unambiguously. An explicit MLF_VERSION
(e.g. ``0.17.1+fl.0.2.0`` for a release build) is used verbatim.

package_info.py is a pure static module (no imports), so setuptools' dynamic
``version = {attr = ...}`` resolves it via AST without importing anything —
rewriting the constants is therefore safe in the torch-free build env.

PEP 440 note: the module joins the version as
``'.'.join(MAJOR.MINOR.PATCH) + PRE_RELEASE``, so a pre-release/stamp must carry
its own leading separator: "0.17.1.post20260812" -> PRE_RELEASE = ".post20260812",
and a provenance local label its own "+": "0.17.1+fl.20260814.gba22f6b673f3" ->
PRE_RELEASE = "+fl.20260814.gba22f6b673f3".
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(os.environ.get("MLF_REPO_DIR", "/opt/megatron-lm-fl"))
PACKAGE_INFO = REPO_DIR / "megatron" / "core" / "package_info.py"

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")
# Line-oriented replaces (package_info.py declares one constant per line).
_CONST_RE = {
    "MAJOR": re.compile(r"^MAJOR = .*$", re.M),
    "MINOR": re.compile(r"^MINOR = .*$", re.M),
    "PATCH": re.compile(r"^PATCH = .*$", re.M),
    "PRE_RELEASE": re.compile(r'^PRE_RELEASE = .*$', re.M),
}


def _const(key: str) -> str:
    return _CONST_RE[key].search(PACKAGE_INFO.read_text()).group(0).split("=", 1)[1].strip()


def _repo_public_version() -> str:
    """Upstream megatron-core version as the checkout currently declares it."""
    return f"{_const('MAJOR')}.{_const('MINOR')}.{_const('PATCH')}" + _const("PRE_RELEASE").strip('"')


def _derive_commit_version() -> str:
    """<public>+fl.<commit-date>.g<short-sha> from the cloned checkout; '' if not a git repo."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_DIR), "show", "-s", "--format=%H%n%cs", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return ""
    if len(out) < 2 or not out[0] or not out[1]:
        return ""
    sha, date = out[0][:12], out[1].replace("-", "")
    return f"{_repo_public_version()}+fl.{date}.g{sha}"


def main() -> int:
    version = os.environ.get("MLF_VERSION", "")
    if not version:
        version = _derive_commit_version()
        if version:
            print(f"MLF_VERSION unset/blank — derived {version} from the git checkout")
        else:
            print("MLF_VERSION unset/blank and no git provenance available — keeping the repo's own version")
            return 0

    m = _VERSION_RE.match(version)
    if not m:
        print(f"ERROR: MLF_VERSION '{version}' is not X.Y.Z[<pre-release>]", file=sys.stderr)
        return 1
    major, minor, patch, pre_release = m.groups()

    src = PACKAGE_INFO.read_text()
    src = _CONST_RE["MAJOR"].sub(f"MAJOR = {major}", src)
    src = _CONST_RE["MINOR"].sub(f"MINOR = {minor}", src)
    src = _CONST_RE["PATCH"].sub(f"PATCH = {patch}", src)
    src = _CONST_RE["PRE_RELEASE"].sub(f'PRE_RELEASE = "{pre_release}"', src)
    PACKAGE_INFO.write_text(src)

    print(f"stamped version {version} into {PACKAGE_INFO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
