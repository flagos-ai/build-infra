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

Creates an orphan branch ``auto/versions-<label>/<backend>`` containing exactly
one file (``<backend>.tsv``) in the empty root tree, then force-pushes it.

Replaces the three ``actions/upload-artifact@v7`` retry-attempt steps in the
extract job, which hang through HTTP_PROXY on some self-hosted runners.

Usage: python scripts/upload_version_tsv.py <backend> <tsv-dir>
"""

import os
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

    subprocess.run(
        ["git", "checkout", "--orphan", branch],
        check=True, cwd=REPO_ROOT,
    )
    # Clean the index (orphan branch starts with a populated index).
    subprocess.run(
        ["git", "rm", "-rf", "--cached", "."],
        check=False, cwd=REPO_ROOT,
    )

    dest = Path(REPO_ROOT) / f"{backend}.tsv"
    dest.write_bytes(tsv_file.read_bytes())

    subprocess.run(
        ["git", "add", f"{backend}.tsv"],
        check=True, cwd=REPO_ROOT,
    )
    subprocess.run(
        ["git", "commit", "-m", f"versions: {backend}"],
        check=True, cwd=REPO_ROOT,
        env={**os.environ, "GIT_AUTHOR_NAME": "flagos-ci",
             "GIT_AUTHOR_EMAIL": "noreply@flagos.net",
             "GIT_COMMITTER_NAME": "flagos-ci",
             "GIT_COMMITTER_EMAIL": "noreply@flagos.net"},
    )
    r = subprocess.run(
        ["git", "push", "-f", "origin", branch],
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
