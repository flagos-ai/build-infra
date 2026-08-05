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

"""Extract the versions of a base image's explicitly-installed system packages,
as actually baked into the built image, via dpkg-query inside the image.

Writes <out-dir>/<name>.tsv with lines "package\tversion" (raw dpkg versions;
gen_descriptions.py cleans them to upstream form). The image ref and the explicit
package list both come from docs/data/images.yaml (run gen_data.py first).

Usage: python docs/extract_versions.py <backend-name> <out-dir>
Requires: docker able to run the image (auto-pulls if logged in and not cached).
"""

import subprocess
import sys
from pathlib import Path

import yaml


def image_labels(image: str) -> dict:
    """Read the last-updated + revision OCI labels via docker inspect.

    The docs pipeline renders these as a "Last updated" line in the base
    description; the values come from build_base.py (git committer time +
    build commit). A missing label prints ``<no value>`` — treat as absent.
    """
    fmt = ('{{index .Config.Labels "last-updated"}}'
           '|{{index .Config.Labels "org.opencontainers.image.revision"}}')
    r = subprocess.run(
        ["docker", "inspect", image, "--format", fmt],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return {}
    ts, _, rev = r.stdout.partition("|")
    out = {}
    if ts and ts != "<no value>":
        out["last_updated"] = ts.strip()
    if rev and rev != "<no value>":
        out["revision"] = rev.strip()
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: extract_versions.py <backend-name> <out-dir>")
    name, out_dir = sys.argv[1], Path(sys.argv[2])
    root = Path(__file__).resolve().parent.parent
    images = yaml.safe_load((root / "docs" / "data" / "images.yaml").read_text())
    entry = next((b for b in images.get("backends", []) if b["name"] == name), None)
    if not entry:
        sys.exit(f"Error: '{name}' not in images.yaml")

    image = entry["base"]["image"]
    pkgs = entry["base"].get("system_packages") or []
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.tsv"

    # Always pull the latest image; docker run --rm uses the local copy but
    # the runner may have a stale cache from a previous build cycle.
    subprocess.run(["docker", "pull", image], check=True, capture_output=True)

    # Record the build provenance labels (written by upload_version_tsv.py
    # into the TSV headers, then rendered by gen_descriptions.py).
    labels = image_labels(image)
    (out_dir / f"{name}.labels").write_text(
        "".join(f"{k}={v}\n" for k, v in labels.items())
    )

    if not pkgs:
        out.write_text("")
        print(f"{name}: no explicit system packages")
        return

    # dpkg-query prints the found packages even when some are absent (it exits
    # non-zero then) — capture stdout regardless.
    cmd = [
        "docker", "run", "--rm", image,
        "dpkg-query", "-W", "-f=${Package}\t${Version}\n", *pkgs,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out.write_text(r.stdout)
    n = len([l for l in r.stdout.splitlines() if "\t" in l])
    print(f"{name}: {n}/{len(pkgs)} package versions from {image}")
    if r.returncode != 0 and n == 0:
        # A real failure (image unrunnable / not dpkg-based), not just a missing pkg.
        sys.stderr.write(r.stderr)
        sys.exit(f"Error: extraction produced no versions for {name}")


if __name__ == "__main__":
    main()
