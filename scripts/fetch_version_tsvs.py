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

"""Fetch TSV files from per-backend extract branches into a local directory.

Each extract job pushes a single ``<backend>.tsv`` to a branch
``auto/versions-<label>/<backend>`` (after individually deleting any stale
branch from a previous cycle).  This script discovers all such branches via
``git ls-remote``, fetches them, and extracts the TSV file into
``<out-dir>/<backend>.tsv``.

Usage:
    python scripts/fetch_version_tsvs.py <out-dir>
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _label() -> str:
    """Version label from the latest git tag, e.g. ``2.1.1``."""
    r = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().lstrip("v")
    return "unknown"


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", help="Path to output directory (versions-remote)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    label = _label()
    prefix = f"refs/heads/auto/versions-{label}/"

    # Discover per-backend branches.
    r = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", f"{prefix}*"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if r.returncode != 0:
        sys.exit(f"Error: git ls-remote failed: {r.stderr.strip()}")

    refs = [line.split()[1] for line in r.stdout.strip().splitlines() if line]
    if not refs:
        print(f"No extract branches found under {prefix}")
        return

    fetched = 0
    for ref in refs:
        backend = ref[len(prefix):]  # e.g. "nvidia-cuda13.3"
        try:
            subprocess.run(
                ["git", "fetch", "origin", ref],
                check=True, capture_output=True, text=True, cwd=REPO_ROOT,
            )
            show = subprocess.run(
                ["git", "show", f"FETCH_HEAD:{backend}.tsv"],
                check=True, capture_output=True, text=True, cwd=REPO_ROOT,
            )
            (out_dir / f"{backend}.tsv").write_text(show.stdout)
            fetched += 1
        except subprocess.CalledProcessError:
            print(f"::warning::Failed to fetch {backend} from {ref}",
                  file=sys.stderr)

    print(f"Fetched {fetched} TSVs from extract branches")


if __name__ == "__main__":
    main()
