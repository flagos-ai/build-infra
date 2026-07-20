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

"""Generate a build matrix for cpp operator wheel backends only.

Like ``scripts/generate_matrix.py``, but filtered to backends that have a
``cmake_backend``. Used by the FlagGems release workflow (step 5b) so only
backends that actually need a cpp wheel are included.

Usage: python3 scripts/generate_cpp_matrix.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent

    import yaml

    configs = yaml.safe_load((root / "configs.yaml").read_text())

    # which backends have cmake_backend?
    cpp_names: set[str] = set()
    for vendor, specs in (configs.get("vendors") or {}).items():
        for bk_name, spec in (specs or {}).items():
            if spec.get("cmake_backend"):
                cpp_names.add(f"{vendor}-{bk_name}")

    # generate full matrix, then filter
    import subprocess

    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "generate_matrix.py")],
        capture_output=True, text=True, cwd=root,
    )
    if r.returncode != 0:
        sys.exit(r.stderr or "generate_matrix.py failed")

    full = json.loads(r.stdout)
    filtered = {
        "include": [e for e in full.get("include", []) if e["name"] in cpp_names],
    }
    json.dump(filtered, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
