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

"""Push the extracted system-package version TSV for a single backend to a git
branch so the accumulate job can collect it without relying on upload-artifact.

Writes the TSV into git's object database directly (hash-object + mktree +
commit-tree + push), never switching branches or touching the working tree.
This keeps the runner's local repo state pristine across runs and avoids the
orphan-branch residue that broke concurrent/retry runs.

Replaces the three ``actions/upload-artifact@v7`` retry-attempt steps in the
extract job, which hang through HTTP_PROXY on some self-hosted runners.

Usage: python scripts/upload_version_tsv.py <backend> <tsv-dir>
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
    if len(sys.argv) != 3:
        sys.exit("usage: upload_version_tsv.py <backend> <tsv-dir>")

    backend = sys.argv[1]
    tsv_dir = Path(sys.argv[2])
    tsv_file = tsv_dir / f"{backend}.tsv"

    if not tsv_file.is_file():
        sys.exit(f"Error: {tsv_file} not found")

    label = _label()
    branch = f"auto/versions-{label}/{backend}"

    # Write the TSV as a git blob, never touching the working tree or index.
    blob = subprocess.run(
        ["git", "hash-object", "-w", str(tsv_file)],
        check=True, capture_output=True, text=True, cwd=REPO_ROOT,
    ).stdout.strip()

    # Build a tree containing just <backend>.tsv.
    tree_input = f"100644 blob {blob}\t{backend}.tsv"
    tree = subprocess.run(
        ["git", "mktree"],
        input=tree_input, check=True, capture_output=True, text=True,
        cwd=REPO_ROOT,
    ).stdout.strip()

    # Create a commit and push directly to the remote branch.
    commit = subprocess.run(
        ["git", "commit-tree", tree, "-m", f"versions: {backend}"],
        input="", check=True, capture_output=True, text=True,
        cwd=REPO_ROOT,
    ).stdout.strip()

    r = subprocess.run(
        ["git", "push", "-f", "origin", f"{commit}:refs/heads/{branch}"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if r.returncode == 0:
        print(f"Pushed {backend}.tsv to {branch}")
    else:
        print(f"::warning::git push failed for {backend} — will be retried",
              file=sys.stderr)
        if r.stderr:
            sys.stderr.write(r.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
