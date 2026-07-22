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

"""Post-collection: generate descriptions and open a PR, or self-trigger a retry.

Two modes, dispatched by ``--done``:

**done=true (finalize)**
    Run ``gen_descriptions.py`` against the collected TSV files, commit the
    changed ``--mode`` pages (base or runtime), and open a PR targeting
    ``main``. Clean up state + per-backend extract branches when done.

**done=false (retry)**
    Self-trigger the ``base-descriptions.yml`` workflow with only the missing
    backends (or exit with a warning if there are none). Clean up the
    per-backend extract branches that were already collected so they don't
    interfere with the next retry. If the retry cap is hit, exit with error.

Usage:
    python scripts/finalize_descriptions.py \\
      --mode base --done true --count 14 --label 2.1.1
    python scripts/finalize_descriptions.py \\
      --mode base --done false --missing "nvidia-cuda13.3 sunrise-tangrt1.2.0" \\
      --retry 3 --max-retries 50 --label 2.1.1
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MODE_CONFIG = {
    "base": {
        "add_paths": [
            "docs/content/en/base/*.md",
            "docs/content/zh-cn/base/*.md",
            "base/*.md",
        ],
        "pr_prefix": "auto/base-descriptions",
        "pr_title": "docs(base): refresh image descriptions for {label}",
        "pr_body": ("Automated refresh with baked-in system-package versions "
                    "for {label}.\n\n**Version data:** {count} backends"),
        "commit_msg": "docs(base): refresh image descriptions for {label}",
    },
    "runtime": {
        "add_paths": [
            "docs/content/en/runtime/*.md",
            "docs/content/zh-cn/runtime/*.md",
            "runtime/*.md",
        ],
        "pr_prefix": "auto/runtime-descriptions",
        "pr_title": "docs(runtime): refresh image descriptions for {label}",
        "pr_body": ("Automated refresh of runtime image descriptions for "
                    "{label}.\n\n**Version data:** {count} backends"),
        "commit_msg": "docs(runtime): refresh image descriptions for {label}",
    },
}


def _git(*args: str, check: bool = True, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        check=check, capture_output=True, text=True,
        cwd=cwd or REPO_ROOT,
    )


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh"] + list(args),
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def _cleanup_per_backend_branches(label: str) -> None:
    """Delete all ``auto/versions-<label>/<backend>`` branches."""
    prefix = f"refs/heads/auto/versions-{label}/"
    r = _git("ls-remote", "--heads", "origin", f"{prefix}*", check=False)
    for line in r.stdout.strip().splitlines():
        ref = line.split()[1]
        branch = ref[len("refs/heads/"):]
        _git("push", "origin", "--delete", branch, check=False)


def _cleanup_state_branch(label: str) -> None:
    _git("push", "origin", "--delete", f"auto/versions-{label}", check=False)


def _git_env() -> dict:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "flagos-ci")
    env.setdefault("GIT_AUTHOR_EMAIL", "noreply@flagos.net")
    env.setdefault("GIT_COMMITTER_NAME", "flagos-ci")
    env.setdefault("GIT_COMMITTER_EMAIL", "noreply@flagos.net")
    return env


def _finalize(args) -> None:
    """Generate descriptions, commit, and open a PR."""
    cfg = MODE_CONFIG[args.mode]
    count = args.count
    label = args.label

    # Ensure git identity is set for the commit.
    _git("config", "user.name", "flagos-ci", check=False)
    _git("config", "user.email", "noreply@flagos.net", check=False)

    # gen_descriptions reads TSV files from VERSIONS_DIR.
    env = _git_env()
    env["VERSIONS_DIR"] = str(REPO_ROOT / "versions")

    subprocess.run(
        [sys.executable, str(REPO_ROOT / "docs" / "gen_descriptions.py")],
        check=True, cwd=REPO_ROOT, env=env,
    )

    # Stage only the files for this mode.
    for pattern in cfg["add_paths"]:
        _git("add", pattern, check=False)

    # Check if anything changed.
    dr = _git("diff", "--cached", "--quiet", check=False)
    if dr.returncode == 0:
        print("No description changes — nothing to PR.")
        # Clean up the stale PR branch from a previous run as well.
        _git("push", "origin", "--delete", f"{cfg['pr_prefix']}-{label}", check=False)
        _cleanup_state_branch(label)
        _cleanup_per_backend_branches(label)
        return

    pr_branch = f"{cfg['pr_prefix']}-{label}"
    cr = _git("checkout", "-b", pr_branch, check=False)
    if cr.returncode != 0:
        _git("checkout", pr_branch)

    _git("commit", "-m", cfg["commit_msg"].format(label=label))

    # Force-push: a stale branch from a previous run (closed/unmerged PR)
    # may already exist with a different commit.
    _git("push", "--force", "origin", pr_branch, check=False)

    # Don't create a duplicate PR if one already exists.
    pr_list = _gh("pr", "list", "--head", pr_branch, "--json", "number", "-q", ".[0].number")
    if not pr_list.stdout.strip():
        _gh(
            "pr", "create",
            "--base", os.environ.get("GITHUB_REF_NAME", "main"),
            "--head", pr_branch,
            "--title", cfg["pr_title"].format(label=label),
            "--body", cfg["pr_body"].format(label=label, count=count),
        )

    _cleanup_state_branch(label)
    _cleanup_per_backend_branches(label)
    print("Done.")


def _retry(args) -> None:
    """Self-trigger the workflow for missing backends."""
    missing = args.missing.strip()
    retry = args.retry
    max_retries = args.max_retries
    label = args.label

    if not missing:
        print("::warning::done=false but no missing backends listed — nothing to retry")
        return

    if retry >= max_retries:
        print(f"::error::Retry cap ({max_retries}) reached. Missing: {missing}")
        _cleanup_per_backend_branches(label)
        _cleanup_state_branch(label)
        sys.exit(1)

    # Per-backend branches from previous successful runs are NOT deleted here —
    # they are the source of truth for already-collected backends. The next
    # accumulate will collect from all existing branches + the freshly pushed
    # ones from this retry, and only merge the latest per-backend TSV.

    next_retry = retry + 1
    print(f"Self-triggering retry {next_retry}/{max_retries} for: {missing}")
    subprocess.run(
        ["gh", "workflow", "run", "Base image descriptions",
         "-f", f"backend={missing}", "-f", f"retry_count={next_retry}"],
        check=True, cwd=REPO_ROOT,
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["base", "runtime"])
    ap.add_argument("--done", required=True, choices=["true", "false"])
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--label", default="unknown")
    ap.add_argument("--missing", default="")
    ap.add_argument("--retry", type=int, default=0)
    ap.add_argument("--max-retries", type=int, default=50)
    args = ap.parse_args()

    if args.done == "true":
        _finalize(args)
    else:
        _retry(args)


if __name__ == "__main__":
    main()
