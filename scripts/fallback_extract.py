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

"""Extract system-package versions from a Harbor image — no hardware needed.

Pulls the image (it's already in Harbor from the build step) and runs dpkg-query.
Used as a compose-phase fallback when the self-hosted runner was unreachable.

Usage: python3 scripts/fallback_extract.py <backend-name> <out-dir>
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: fallback_extract.py <backend-name> <out-dir>")
    name, out_dir = sys.argv[1], Path(sys.argv[2])

    images = yaml.safe_load((ROOT / "docs" / "data" / "images.yaml").read_text())
    entry = next((b for b in images.get("backends", []) if b["name"] == name), None)
    if not entry:
        sys.exit(f"Error: '{name}' not in images.yaml")

    image = entry["base"]["image"]
    pkgs = entry["base"].get("system_packages") or []
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.tsv"

    if not pkgs:
        out.write_text("")
        print(f"{name}: no explicit system packages")
        return

    # Pull first — compose runner may not have the image cached.
    subprocess.run(["docker", "pull", image], check=True)

    cmd = [
        "docker", "run", "--rm", image,
        "dpkg-query", "-W", "-f=${Package}\t${Version}\n", *pkgs,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out.write_text(r.stdout)
    n = len([l for l in r.stdout.splitlines() if "\t" in l])
    print(f"{name}: {n}/{len(pkgs)} package versions from {image}")
    if r.returncode != 0 and n == 0:
        sys.stderr.write(r.stderr or "")
        sys.exit(f"Error: extraction produced no versions for {name}")


if __name__ == "__main__":
    main()
