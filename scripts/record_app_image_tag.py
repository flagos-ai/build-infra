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

"""Record a pushed app image tag into the status matrix and refresh the docs.

Called by the app-image build workflows right after ``docker push`` — the push
is the publication event, and the workflow is the only place that knows the
exact tag at push time. The status matrix ``image_tag`` is the single source of
truth for "this backend is published" (see docs/status-matrix.md), so the
workflow writes it there itself instead of leaving it to a human verifier.

What the script does, in order:
  1. Update ``image_tag`` and set ``launch_docs: true`` + ``deps_app: true``
     for the backend in the status matrix YAML (surgical line edit — the matrix
     files carry a human header comment that a YAML round-trip would drop).
     Also drops a backend note of the form "验证 ✅，app 镜像未推送/未发布"
     — the push just recorded makes it stale by construction.
     Idempotent: all three facts already recorded → no-op, exit 0.
  2. Regenerate the pipeline so the docs stay consistent with the matrix:
     ``gen_data.py`` → ``render_status_matrix.py`` → ``gen_descriptions.py
     --app-only`` (app pages read no version TSVs, so no VERSIONS_DIR).
  3. Commit the changed matrix + app pages as ``flagos-ci``, push (or
     recreate) the ``auto/app-image-tag`` branch, and open (or update) a
     review-gated PR against the workflow's ref — the same dup-PR pattern as
     status-matrix-consistency.yml. PR ops go through the REST API via curl
     (``GITHUB_TOKEN``), not the ``gh`` CLI — the step runs on self-hosted
     hardware runners that do not carry gh.

``launch_docs`` and ``deps_app`` are set alongside ``image_tag`` because step 2
regenerates the app launch pages — a pushed backend's launch docs exist by
construction, and a pushed backend is buildable by construction (the workflow
only builds a backend whose ``deps_app`` key exists in configs.yaml), so
human-tracking booleans here only drift from reality.

Usage:
    python scripts/record_app_image_tag.py \\
      --matrix packaging/vllm/status_matrix.vllm0.20.2.yaml \\
      --backend nvidia-cuda13.3 \\
      --tag harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda13.3:2.1.2-0.2.1_g825c1cd
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "flagos-ci",
    "GIT_AUTHOR_EMAIL": "noreply@flagos.net",
    "GIT_COMMITTER_NAME": "flagos-ci",
    "GIT_COMMITTER_EMAIL": "noreply@flagos.net",
}

BRANCH = "auto/app-image-tag"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args), check=check, capture_output=True, text=True, cwd=REPO_ROOT
    )


def _run_py(script: Path, *args: str) -> None:
    subprocess.run(
        [sys.executable, str(script)] + list(args),
        check=True, cwd=REPO_ROOT, env=_env(),
    )


def _env() -> dict:
    env = os.environ.copy()
    for k, v in GIT_IDENTITY.items():
        env.setdefault(k, v)
    return env


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


def _backend_bounds(lines: list[str], backend: str) -> tuple[int, int]:
    """Return the (start, end) line indices of the backend's facility block.

    The matrix format is stable: backend keys sit at 2-space indent, their
    facility fields (deps_app / launch_docs / image_tag / prs) at 4-space, so a
    backend block runs from its key line to the next 2-space key line (or the
    mapping end).
    """
    start = None
    for i, ln in enumerate(lines):
        if re.match(rf"^  {re.escape(backend)}:$", ln):
            start = i
            break
    if start is None:
        sys.exit(f"Error: backend '{backend}' not found")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j] and (not lines[j][0].isspace() or re.match(r"^  [^ ]", lines[j])):
            end = j
            break
    return start, end


def _set_facility_field(matrix_path: Path, backend: str, field: str, value: str) -> bool:
    """Set a facility field for the backend; return True if the file changed.

    Surgical line edit to preserve the header comment block. Existing field →
    replace in place; absent field → insert after the last known facility field
    (deps_app / launch_docs), before any prs list.
    """
    lines = matrix_path.read_text().splitlines()
    start, end = _backend_bounds(lines, backend)
    block = lines[start + 1:end]

    new_line = f"    {field}: {value}"
    for k, ln in enumerate(block):
        if re.match(rf"^    {field}:\s*", ln):
            if ln == new_line:
                return False
            lines[start + 1 + k] = new_line
            matrix_path.write_text("\n".join(lines) + "\n")
            return True

    insert_at = start + 1
    for k, ln in enumerate(block):
        if re.match(r"^    (deps_app|launch_docs):", ln):
            insert_at = start + 1 + k + 1
    lines.insert(insert_at, new_line)
    matrix_path.write_text("\n".join(lines) + "\n")
    return True


def update_image_tag(matrix_path: Path, backend: str, tag: str) -> bool:
    """Update image_tag for the backend; return True if the file changed."""
    return _set_facility_field(matrix_path, backend, "image_tag", f'"{tag}"')


def update_launch_docs(matrix_path: Path, backend: str) -> bool:
    """Set launch_docs: true for the backend; return True if the file changed.

    The record step regenerates the app launch pages right after recording the
    push, so a published backend's launch docs exist by construction — set the
    boolean alongside image_tag (one publication event, both facts) instead of
    leaving it to drift as a human-tracking flag.
    """
    return _set_facility_field(matrix_path, backend, "launch_docs", "true")


def update_deps_app(matrix_path: Path, backend: str) -> bool:
    """Set deps_app: true for the backend; return True if the file changed.

    A pushed backend is buildable by construction — the app-image workflow only
    builds a backend whose ``deps_app`` key exists in configs.yaml (key presence
    gates the build). Recording the push therefore proves the key exists, so set
    the matrix boolean alongside image_tag instead of leaving it to drift as a
    human-tracking flag.
    """
    return _set_facility_field(matrix_path, backend, "deps_app", "true")


def clear_stale_note(matrix_path: Path, backend: str) -> bool:
    """Drop the backend's note if it claims the image was never pushed.

    A note of the form "验证 ✅，app 镜像未推送/未发布" becomes stale the moment
    ``image_tag`` is written — the push is the publication event, so the two
    facts cannot both hold. Notes carrying other content (F-path failures,
    ABI blockers, deliberate holds) are left alone.
    """
    lines = matrix_path.read_text().splitlines()
    start, end = _backend_bounds(lines, backend)
    block = lines[start + 1:end]
    for k, ln in enumerate(block):
        if re.match(r'^    note:\s+"验证 ✅，app 镜像未(推送|发布)', ln):
            del lines[start + 1 + k]
            matrix_path.write_text("\n".join(lines) + "\n")
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, help="status matrix YAML path, relative to repo root")
    parser.add_argument("--backend", required=True, help="backend key in the matrix")
    parser.add_argument("--tag", required=True, help="full pushed image ref (tag taken after the last ':')")
    args = parser.parse_args()

    matrix_rel = args.matrix
    matrix_path = REPO_ROOT / matrix_rel
    if not matrix_path.is_file():
        sys.exit(f"Error: matrix file not found: {matrix_rel}")
    tag = args.tag.rsplit(":", 1)[-1]

    # A stale "未推送" note contradicts image_tag by construction — clear it
    # before the idempotency check so already-recorded backends self-heal.
    changed = clear_stale_note(matrix_path, args.backend)

    # Idempotency: all three facts already recorded → nothing to do.
    backend_cfg = (yaml.safe_load(matrix_path.read_text()) or {}).get("backends", {}).get(args.backend, {})
    if (backend_cfg.get("image_tag", "") == tag and backend_cfg.get("launch_docs", False)
            and backend_cfg.get("deps_app", False)):
        if not changed:
            print(f"{args.backend} already records image_tag {tag} + launch_docs + deps_app — nothing to do.")
        return
    print(f"Recording image_tag {tag} + launch_docs + deps_app for {args.backend} in {matrix_rel}")

    changed = update_image_tag(matrix_path, args.backend, tag) or changed
    changed = update_launch_docs(matrix_path, args.backend) or changed
    changed = update_deps_app(matrix_path, args.backend) or changed
    if not changed:
        return

    comp = component_of(matrix_rel)

    # Refresh the pipeline so matrix, verification md, and app pages agree.
    _run_py(REPO_ROOT / "docs" / "gen_data.py")
    _run_py(REPO_ROOT / "scripts" / "render_status_matrix.py", "--component", comp)
    _run_py(REPO_ROOT / "docs" / "gen_descriptions.py", "--app-only")

    # Stage only the artifacts this record touches.
    for pattern in (matrix_rel, "packaging/*/docs/*-verification-matrix.md",
                    "docs/content/en/application/*.md", "docs/content/zh-cn/application/*.md"):
        _git("add", pattern, check=False)
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("No doc changes after recording tag — nothing to PR.")
        return

    commit_msg = f"chore({comp}): record app image tag {tag} for {args.backend}"
    for k, v in GIT_IDENTITY.items():
        os.environ.setdefault(k, v)
    _git("config", "user.name", "flagos-ci", check=False)
    _git("config", "user.email", "noreply@flagos.net", check=False)
    _git("checkout", "-B", BRANCH, check=False)
    _git("commit", "-m", commit_msg)

    # The record PR's merge deletes this branch (delete_branch_on_merge), so
    # ask origin, not the (possibly stale) local mirror, whether it exists.
    probe = _git("ls-remote", "origin", f"refs/heads/{BRANCH}", check=False)
    if probe.returncode == 0 and probe.stdout.strip():
        # Another record sits on the branch: rebase onto it, then plain-push —
        # we are its descendant, and --force would clobber that record.
        _git("fetch", "origin", BRANCH, check=False)
        if _git("rebase", f"origin/{BRANCH}", check=False).returncode != 0:
            _git("rebase", "--abort", check=False)
            sys.exit(
                f"Error: {BRANCH} already carries a conflicting record — merge or close its "
                f"PR, then re-run the workflow (or dispatch record-app-image-tag.yml to "
                f"record without a rebuild) to record {tag}"
            )
        _git("push", "origin", BRANCH)
    else:
        # Branch deleted: recreate from fresh main so the regenerated pages
        # embed records merged since this run was dispatched.
        _git("fetch", "origin", "main", check=False)
        if _git("rebase", "origin/main", check=False).returncode != 0:
            _git("rebase", "--abort", check=False)
            sys.exit(
                f"Error: {BRANCH} is absent but this run's base conflicts with origin/main — "
                f"re-run the workflow (or dispatch record-app-image-tag.yml to record "
                f"without a rebuild) to record {tag}"
            )
        _git("push", "origin", BRANCH)

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
        f"The {comp} app-image workflow pushed an image for `{args.backend}` and recorded "
        f"the published tag `{tag}` into the status matrix. This PR brings the matrix, the "
        "verification matrix, and the app launch pages back in sync — no functional changes. "
        "Schema and refresh mechanism: docs/status-matrix.md."
    )
    _gh_api("POST", f"/repos/{repo}/pulls", {
        "title": commit_msg,
        "head": BRANCH,
        "base": base,
        "body": body,
    })


if __name__ == "__main__":
    main()
