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

"""Open/update the review-gated PR for a verify-driver record round.

Run by the verify-driver record job after verify_record_results.py has applied
the per-cell symbols, appended failed cells to the debug queue, and written
``.github/verify-remaining.json``. This script closes the round:

  1. Re-render the changed matrices' verification md
     (``render_status_matrix.py --component``).
  2. Commit the matrix + queue + rendered md as ``flagos-ci`` on branch
     ``auto/verify-results``, rebase onto the remote tip, force-push.
  3. Open (or update) a review-gated PR via the REST API — the same dup-PR +
     force-push pattern as record_app_image_tag.py.

It never merges. Requires GH_TOKEN/GITHUB_TOKEN and GITHUB_REPOSITORY.

Usage:
    python scripts/verify_open_pr.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "flagos-ci",
    "GIT_AUTHOR_EMAIL": "noreply@flagos.net",
    "GIT_COMMITTER_NAME": "flagos-ci",
    "GIT_COMMITTER_EMAIL": "noreply@flagos.net",
}

BRANCH = "auto/verify-results"
REMAINING_PATH = REPO_ROOT / ".github" / "verify-remaining.json"
QUEUE_REL = ".github/verify-queue.yaml"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args), check=check, capture_output=True, text=True, cwd=REPO_ROOT
    )


def _run_py(script: Path, *args: str) -> None:
    env = os.environ.copy()
    for k, v in GIT_IDENTITY.items():
        env.setdefault(k, v)
    subprocess.run([sys.executable, str(script)] + list(args), check=True, cwd=REPO_ROOT, env=env)


def _gh_api(method: str, path: str, body: dict | None = None) -> dict:
    """Call the GitHub REST API with GITHUB_TOKEN (no gh CLI dependency)."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Error: GH_TOKEN/GITHUB_TOKEN not set — cannot open a PR")
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def component_of(matrix_rel: str) -> str:
    m = re.match(r"packaging/(\w+)/status_matrix\.", matrix_rel)
    if not m:
        sys.exit(f"Error: cannot derive component from matrix path '{matrix_rel}'")
    return m.group(1)


def main() -> None:
    remaining = {}
    if REMAINING_PATH.is_file():
        remaining = json.loads(REMAINING_PATH.read_text())
    changed = remaining.get("changed", [])

    comps = sorted({component_of(p) for p in changed})
    for comp in comps:
        _run_py(REPO_ROOT / "scripts" / "render_status_matrix.py", "--component", comp)

    for rel in changed:
        _git("add", rel, check=False)
    _git("add", QUEUE_REL, check=False)
    _git("add", "packaging/*/docs/*-verification-matrix.md", check=False)
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("verify_open_pr: no staged changes — nothing to PR.")
        return

    n = len(changed)
    commit_msg = f"chore(verify): record {n} cell result(s) from verify-driver"
    for k, v in GIT_IDENTITY.items():
        os.environ.setdefault(k, v)
    _git("config", "user.name", "flagos-ci", check=False)
    _git("config", "user.email", "noreply@flagos.net", check=False)
    _git("checkout", "-B", BRANCH, check=False)
    _git("commit", "-m", commit_msg)

    # Rebase our commit onto the remote tip and force-push. The record job is
    # serialized by a workflow concurrency guard, but the branch can still move
    # from a manual push or a duplicate cell — retry a few times so a transient
    # move doesn't drop this round's results instead of hard-exiting.
    for attempt in range(5):
        _git("fetch", "origin", BRANCH, check=False)
        if _git("rev-parse", "--verify", f"origin/{BRANCH}", check=False).returncode == 0:
            if _git("rebase", f"origin/{BRANCH}", check=False).returncode != 0:
                _git("rebase", "--abort", check=False)
                continue  # remote tip moved under us — re-fetch and retry
        try:
            _git("push", "--force", "origin", BRANCH)
            break
        except subprocess.CalledProcessError:
            continue  # transient push failure — retry
    else:
        sys.exit(
            f"Error: could not push {BRANCH} after 5 attempts — the branch kept "
            f"moving concurrently; re-run the driver to record this round"
        )

    base = os.environ.get("GITHUB_REF_NAME", "main")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        sys.exit("Error: GITHUB_REPOSITORY not set — cannot open a PR")
    existing = _gh_api(
        "GET", f"/repos/{repo}/pulls?head={repo.split('/', 1)[0]}:{BRANCH}&state=open"
    )
    if existing:
        print(f"PR already open for {BRANCH}; force-pushed updated content")
        return
    body = (
        "The verify driver applied this round's cell results to the status matrices and "
        "appended any failed cells to the debug queue. This PR brings the matrices, the "
        "verification matrices, and the queue back in sync — no functional changes. "
        "Opened as a draft: the cells' exit codes do not yet guarantee a clean end-to-end "
        "install, so confirm each ✅ before marking ready for review. "
        "Driver + queue schema: docs/verify-orchestrator.md."
    )
    _gh_api("POST", f"/repos/{repo}/pulls", {
        "title": commit_msg,
        "head": BRANCH,
        "base": base,
        "body": body,
        "draft": True,
    })


if __name__ == "__main__":
    main()
