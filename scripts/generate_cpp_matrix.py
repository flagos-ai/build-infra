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
``cmake_backend``, with one entry per unique cmake_backend value — the cpp
wheel for ``CUDA`` is the same for nvidia-cuda12.8 and nvidia-cuda13.3.

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

    # Map cmake_backend -> one backend name (first encountered).
    cpp_map: dict[str, str] = {}
    for vendor, specs in (configs.get("vendors") or {}).items():
        for bk_name, spec in (specs or {}).items():
            cmake = spec.get("cmake_backend")
            if cmake and cmake not in cpp_map:
                cpp_map[cmake] = f"{vendor}-{bk_name}"

    cpp_names = set(cpp_map.values())

    # generate full matrix, then filter
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
