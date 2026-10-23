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

"""Record a runtime image push: date its changelog entry and open a PR.

Called by runtime-image.yml right after ``docker push``, once per backend. The
push is the publication event, and the registry's push_time is the only honest
date for it, so the pending entry that authorized the rebuild (reason, empty
date — written by a human before the dispatch) is dated with it here instead
of by hand.

This is the runtime half of the app layer's ``record_app_image_tag.py``, and it
is smaller by construction: the runtime layer has no status matrix, no launch
page and no ``image_tag`` field, so the changelog is all there is to record.
It is also run once per backend rather than once per dispatch, because each
matrix job is the only place that knows its own image reached the registry —
a dispatch-level job cannot tell a pushed backend from one whose build failed,
and dating a failed backend's entry with the previous push's push_time would
record a rebuild that never happened.

Every backend a dispatch pushes records onto one branch (one per tag) and one
PR — this is a changelog fan-out, not a matrix rewrite — so the push is retried
against the concurrent writers from the same dispatch. The tag is an input, not
derived here, so the recorded date always belongs to the image that was really
pushed (including the ``-build`` variant).

Usage:
    python scripts/record_runtime_image.py metax-maca3.8.1.3 \\
      harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.8.1.3:2.3.0
    python scripts/record_runtime_image.py metax-maca3.8.1.3 <ref> --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HARBOR_API = "https://harbor.baai.ac.cn/api/v2.0"

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
    """Call the GitHub REST API with GITHUB_TOKEN (no gh CLI dependency).

    The record step runs on a self-hosted hardware runner, which carries no gh.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Error: GH_TOKEN/GITHUB_TOKEN not set — cannot open a PR")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"https://api.github.com{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def harbor_push_time(image_ref: str) -> str:
    """Registry push_time (RFC3339) for a full image ref."""
    path, _, tag = image_ref.rpartition(":")
    parts = path.split("/")
    if len(parts) < 2 or not tag:
        sys.exit(f"Error: cannot parse image ref '{image_ref}'")
    url = f"{HARBOR_API}/projects/{parts[-2]}/repositories/{parts[-1]}/artifacts/{tag}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            push_time = json.load(resp).get("push_time")
    except urllib.error.HTTPError as exc:
        sys.exit(
            f"Error: registry has no artifact {image_ref} ({exc.code}) — nothing was "
            f"pushed under that tag, so there is no date to record"
        )
    if not push_time:
        sys.exit(f"Error: registry returned no push_time for {image_ref}")
    return push_time


def push_branch(branch: str, commit_msg: str) -> None:
    """Commit onto the tag's branch and push, rebasing past concurrent writers.

    A dispatch records every backend it pushed and they all target this branch,
    so a push can lose the race; the loser rebases onto whatever landed and
    retries. Bounded, because a conflict that survives a rebase is not a race.
    """
    _git("checkout", "-B", branch, check=False)
    _git("commit", "-m", commit_msg)

    last_error = ""
    for attempt in range(1, 6):
        # Ask origin, not a local ref: this branch is deleted when its PR
        # merges, so a stale local ref would misreport it as present.
        probe = _git("ls-remote", "origin", f"refs/heads/{branch}", check=False)
        upstream = branch if (probe.returncode == 0 and probe.stdout.strip()) else "main"
        _git("fetch", "origin", upstream, check=False)
        if _git("rebase", f"origin/{upstream}", check=False).returncode != 0:
            _git("rebase", "--abort", check=False)
            # The rebase replays this commit onto the upstream's copy of the
            # same files; a conflict here is a real one, not a race.
            sys.exit(
                f"Error: cannot rebase this record onto origin/{upstream} — inspect "
                f"{branch} and re-run"
            )
        pushed = _git("push", "origin", f"HEAD:refs/heads/{branch}", check=False)
        if pushed.returncode == 0:
            return
        last_error = (pushed.stderr or pushed.stdout).strip()
        print(f"push attempt {attempt} lost the race, retrying: {last_error}")
        time.sleep(5 * attempt)
    sys.exit(f"Error: could not push {branch} after 5 attempts — {last_error}")


def open_pr(branch: str, commit_msg: str, tag: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        sys.exit("Error: GITHUB_REPOSITORY not set — cannot open a PR")
    head = f"{repo.split('/', 1)[0]}:{branch}"
    existing = _gh_api("GET", f"/repos/{repo}/pulls?head={head}&state=open")
    if existing:
        print(f"PR #{existing[0]['number']} already open for {branch}; pushed the update")
        return

    body = (
        f"The runtime-image workflow pushed `{tag}` and dated each backend's pending "
        "changelog entry with its registry push_time — the entry that authorized "
        "the rebuild. No image content is changed here; this records that the "
        "rebuilds happened, and why. One dispatch records every backend it pushed "
        "on this branch, so this PR fills up as the matrix proceeds.\n\n"
        "Schema and rules: docs/changelog.md.\n\n"
        "This PR was written in part with the assistance of generative AI."
    )
    try:
        pr = _gh_api("POST", f"/repos/{repo}/pulls", {
            "title": commit_msg,
            "head": branch,
            "base": os.environ.get("GITHUB_REF_NAME", "main"),
            "body": body,
        })
    except urllib.error.HTTPError as exc:
        # A concurrent backend created it between the lookup and the POST.
        if exc.code != 422:
            raise
        print(f"PR for {branch} was created concurrently; nothing to do")
        return
    print(f"opened PR #{pr['number']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", help="backend key, e.g. metax-maca3.8.1.3")
    parser.add_argument("image", help="full pushed image ref (with the tag)")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve the push time and stop (no writes, no PR)")
    args = parser.parse_args()

    tag = args.image.rpartition(":")[2]
    if not tag or "/" in tag:
        sys.exit(f"Error: '{args.image}' carries no tag")
    changelog = f"runtime/changelogs/{args.backend}.yaml"
    if not (REPO_ROOT / changelog).is_file():
        sys.exit(f"Error: {changelog} is missing — every runtime row needs one")

    push_time = harbor_push_time(args.image)
    print(f"{args.backend}: {args.image} pushed at {push_time}")
    if args.dry_run:
        return

    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "backfill_changelog_date.py"),
         changelog, tag, push_time],
        check=True, cwd=REPO_ROOT,
    )
    if _git("diff", "--quiet", "--", changelog, check=False).returncode == 0:
        print(f"{changelog}: tag {tag} was already dated — nothing to record")
        return

    for k, v in GIT_IDENTITY.items():
        os.environ.setdefault(k, v)
    _git("config", "user.name", "flagos-ci", check=False)
    _git("config", "user.email", "noreply@flagos.net", check=False)
    _git("add", changelog, check=False)
    commit_msg = f"chore(runtime): record changelog date for {tag} ({args.backend})"
    branch = f"auto/runtime-changelog-{tag}"
    push_branch(branch, commit_msg)
    open_pr(branch, commit_msg, tag)


if __name__ == "__main__":
    main()
