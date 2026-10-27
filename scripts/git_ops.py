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

"""The git and GitHub operations every record script needs.

A record always ends the same way — a commit onto a per-record branch, a push
that survives concurrent writers, a review-gated PR — so that half lives here
instead of once per script. What the commit *is* stays with its producer.

The record step runs on a self-hosted hardware runner, which carries no gh CLI
— hence the REST calls instead of shelling out.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "flagos-ci",
    "GIT_AUTHOR_EMAIL": "noreply@flagos.net",
    "GIT_COMMITTER_NAME": "flagos-ci",
    "GIT_COMMITTER_EMAIL": "noreply@flagos.net",
}


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args), check=check, capture_output=True, text=True, cwd=REPO_ROOT
    )


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


def configure_git_identity() -> None:
    for k, v in GIT_IDENTITY.items():
        os.environ.setdefault(k, v)
    _git("config", "user.name", "flagos-ci", check=False)
    _git("config", "user.email", "noreply@flagos.net", check=False)


def push_record_branch(branch: str, commit_msg: str, attempts: int = 5) -> None:
    """Commit onto the record's branch and push, rebasing past concurrent writers.

    The commit must already be staged; this only creates the branch, commits and
    pushes. The branch is rebased onto whatever landed meanwhile: the branch
    itself while it still exists (a re-run or a recovery rebases onto the record
    already there), origin/main once it is gone (the branch is deleted when its
    PR merges, so recreating from main lets the record carry everything merged
    since the run was dispatched).

    One dispatch records several artifacts onto one branch, so a push can lose
    the race; the loser re-probes and retries. Bounded, because a conflict that
    survives a rebase is not a race.
    """
    configure_git_identity()
    _git("checkout", "-B", branch, check=False)
    _git("commit", "-m", commit_msg)

    last_error = ""
    for attempt in range(1, attempts + 1):
        # Ask origin, not a local ref: this branch is deleted when its PR
        # merges, so a stale local ref would misreport it as present.
        probe = _git("ls-remote", "origin", f"refs/heads/{branch}", check=False)
        upstream = branch if (probe.returncode == 0 and probe.stdout.strip()) else "main"
        _git("fetch", "origin", upstream, check=False)
        if _git("rebase", f"origin/{upstream}", check=False).returncode != 0:
            _git("rebase", "--abort", check=False)
            # The rebase replays this commit onto the upstream's copy of the
            # same files; a conflict here is a real one, not a race.
            where = (
                f"{branch} already carries a record for this push — merge or close its PR"
                if upstream == branch else
                "this run's base conflicts with origin/main — re-run the workflow"
            )
            sys.exit(f"Error: cannot rebase onto origin/{upstream}: {where}")
        pushed = _git("push", "origin", f"HEAD:refs/heads/{branch}", check=False)
        if pushed.returncode == 0:
            return
        last_error = (pushed.stderr or pushed.stdout).strip()
        print(f"push attempt {attempt} lost the race, retrying: {last_error}")
        time.sleep(5 * attempt)
    sys.exit(f"Error: could not push {branch} after {attempts} attempts — {last_error}")


def open_pr(branch: str, title: str, body: str, base: str = "") -> None:
    """Open (or report) the review-gated PR for a record branch."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        sys.exit("Error: GITHUB_REPOSITORY not set — cannot open a PR")
    head = f"{repo.split('/', 1)[0]}:{branch}"
    existing = _gh_api("GET", f"/repos/{repo}/pulls?head={head}&state=open")
    if existing:
        print(f"PR #{existing[0]['number']} already open for {branch}; pushed the update")
        return
    try:
        pr = _gh_api("POST", f"/repos/{repo}/pulls", {
            "title": title,
            "head": branch,
            "base": base or os.environ.get("GITHUB_REF_NAME", "main"),
            "body": body,
        })
    except urllib.error.HTTPError as exc:
        # A concurrent record created it between the lookup and the POST.
        if exc.code != 422:
            raise
        print(f"PR for {branch} was created concurrently; nothing to do")
        return
    print(f"opened PR #{pr['number']}")
