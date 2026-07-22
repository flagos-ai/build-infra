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
branch so the accumulate job can collect it.

Preconditions: the caller records the verify step outcome to
``<tsv-dir>/<backend>.verify_outcome`` (contents: ``success``, ``failure``,
or ``skipped``).  ``GITHUB_RUN_ID`` must be set in the environment.

The script prepends two metadata headers (``# run:``, ``# verify:``) to the
TSV so the accumulate job can tell whether the data is fresh and whether the
verify step passed.

Before pushing, deletes the remote branch so a failed extract leaves no stale
branch behind.

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
    verify_file = tsv_dir / f"{backend}.verify_outcome"

    if not tsv_file.is_file():
        sys.exit(f"Error: {tsv_file} not found")

    label = _label()
    branch = f"auto/versions-{label}/{backend}"
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    verify = verify_file.read_text().strip() if verify_file.is_file() else "unknown"

    # Prepend metadata headers to the TSV content.
    tsv_raw = tsv_file.read_text()
    payload = f"# run: {run_id}\n# verify: {verify}\n{tsv_raw}"

    # Delete any stale branch so a failed extract leaves no trace.
    subprocess.run(
        ["git", "push", "origin", "--delete", branch],
        check=False, capture_output=True, cwd=REPO_ROOT,
    )

    # Write the annotated TSV as a git blob, never touching the working tree.
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        input=payload, check=True, capture_output=True, text=True,
        cwd=REPO_ROOT,
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
        check=True, capture_output=True, text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "GIT_AUTHOR_NAME": "flagos-ci",
             "GIT_AUTHOR_EMAIL": "noreply@flagos.net",
             "GIT_COMMITTER_NAME": "flagos-ci",
             "GIT_COMMITTER_EMAIL": "noreply@flagos.net"},
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
