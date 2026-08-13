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
``megatron/core/package_info.py``. Blank MLF_VERSION is a no-op (the repo's own
version, e.g. 0.17.1, is used).

package_info.py is a pure static module (no imports), so setuptools' dynamic
``version = {attr = ...}`` resolves it via AST without importing anything —
rewriting the constants is therefore safe in the torch-free build env.

PEP 440 note: the module joins the version as
``'.'.join(MAJOR.MINOR.PATCH) + PRE_RELEASE``, so a pre-release/stamp must carry
its own leading separator: "0.17.1.post20260812" -> PRE_RELEASE = ".post20260812".
"""

import os
import re
import sys
from pathlib import Path

PACKAGE_INFO = Path("/opt/megatron-lm-fl/megatron/core/package_info.py")

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")
# Line-oriented replaces (package_info.py declares one constant per line).
_CONST_RE = {
    "MAJOR": re.compile(r"^MAJOR = .*$", re.M),
    "MINOR": re.compile(r"^MINOR = .*$", re.M),
    "PATCH": re.compile(r"^PATCH = .*$", re.M),
    "PRE_RELEASE": re.compile(r'^PRE_RELEASE = .*$', re.M),
}


def main() -> int:
    version = os.environ.get("MLF_VERSION", "")
    if not version:
        print("MLF_VERSION unset/blank — keeping the repo's own version")
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
