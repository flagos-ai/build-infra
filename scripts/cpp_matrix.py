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

"""Generate a cpp wheel build matrix: only cmake_backend backends."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    import yaml

    configs = yaml.safe_load((ROOT / "configs.yaml").read_text())
    cpp: set[str] = set()
    for vendor, bks in (configs.get("vendors") or {}).items():
        for bk, spec in (bks or {}).items():
            if spec.get("cmake_backend"):
                cpp.add(f"{vendor}-{bk}")

    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_matrix.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    if r.returncode != 0:
        sys.exit(r.stderr or "generate_matrix.py failed")
    full = json.loads(r.stdout)
    filtered = {
        "include": [e for e in full.get("include", []) if e["name"] in cpp],
    }
    json.dump(filtered, sys.stdout)
    print()


if __name__ == "__main__":
    main()
