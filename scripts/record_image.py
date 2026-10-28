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

"""Record a pushed image into its layer's tree and open a review-gated PR.

Called by the image workflows right after ``docker push``. The push is the
publication event, and the job that pushed is the only place that knows which
ref reached the registry, so the record is written here. The registry's
``push_time`` is the date it carries, never a hand-typed one.

``--layer`` picks the tree the record lands in. The three layers differ in
exactly one thing — what "published" has to be written down as:

  base / runtime
      the pending changelog entry that authorized the rebuild (reason, empty
      date, written by a human before the dispatch) is dated. Neither layer has
      a status matrix, so the changelog is all there is to record.
  app
      the status matrix's ``image_tag`` — the single source of truth for "this
      backend is published" (docs/status-matrix.md) — plus ``launch_docs`` and
      ``deps_app``, plus the same changelog date. The docs pipeline is then
      re-run so the verification matrix and the app launch pages agree with
      what was just recorded.

The Harbor query, the rebase-and-retry push and the PR are identical across
the three; the git and GitHub half lives in ``git_ops``.

Every layer records once per dispatched matrix job rather than once per
dispatch, because each job is the only place that knows its own image reached
the registry. A dispatch-level job cannot tell a pushed backend from one whose
build failed, and dating a failed backend's entry with the previous push's
``push_time`` would record a rebuild that never happened.

Usage:
    python scripts/record_image.py --layer base --backend hygon-dtk26.04 \\
      --tag harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.3.0
    python scripts/record_image.py --layer runtime --backend metax-maca3.8.1.3 \\
      --tag harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.8.1.3:2.3.0
    python scripts/record_image.py --layer app \\
      --matrix packaging/vllm/status_matrix.vllm0.24.0.yaml \\
      --backend nvidia-cuda12.8 \\
      --changelog "app/vllm/changelogs/vllm0.24.0-generic-12.8.yaml" \\
      --tag harbor.baai.ac.cn/flagos-app/vllm0.24.0-generic-12.8:2.3.0-0.2.1
    python scripts/record_image.py --layer base --backend hygon-dtk26.04 \\
      --tag <ref> --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_ops import (  # noqa: E402
    REPO_ROOT,
    _gh_api,
    _git,
    configure_git_identity,
    open_pr,
    push_record_branch,
)

DISCLOSURE = "This PR was written in part with the assistance of generative AI."

HARBOR_API = "https://harbor.baai.ac.cn/api/v2.0"


def _run_py(script: Path, *args: str) -> None:
    subprocess.run(
        [sys.executable, str(script)] + list(args), check=True, cwd=REPO_ROOT
    )


def harbor_push_time(image_ref: str) -> str:
    """Registry push_time (RFC3339) for a full image ref.

    Anonymous read works on this Harbor; no token needed. A missing artifact is
    fatal rather than empty: it means nothing was pushed under that tag, so
    there is no date to record and the record must not invent one.
    """
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


# ── base / runtime: date the changelog entry ────────────────────────────────


def _changelog_pages(layer: str, backend: str) -> list[str]:
    """Every base/runtime file carrying this backend's Changelog section.

    The dated entry has to reach the layer's readers, and the section is
    appended to the generated pages rather than rendered into their bodies, so
    it is rebuilt here — right after the date exists — and staged with the
    changelog. Merging the record PR then republishes the Harbor description
    through the layer's existing pubdoc workflow.
    """
    return [
        f"docs/content/{lang}/{layer}/{backend}.md" for lang in ("en", "zh-cn")
    ] + [f"{layer}/{backend}.md"]


def record_changelog(layer: str, backend: str, ref: str, tag: str, dry_run: bool) -> None:
    changelog = f"{layer}/changelogs/{backend}.yaml"
    if not (REPO_ROOT / changelog).is_file():
        sys.exit(f"Error: {changelog} is missing — every {layer} row needs one")

    push_time = harbor_push_time(ref)
    print(f"{backend}: {ref} pushed at {push_time}")
    if dry_run:
        return

    _run_py(REPO_ROOT / "scripts" / "backfill_changelog_date.py", changelog, tag, push_time)
    if _git("diff", "--quiet", "--", changelog, check=False).returncode == 0:
        print(f"{changelog}: tag {tag} was already dated — nothing to record")
        return

    # The entry is dated, so it is now publishable: rebuild the Changelog
    # section of this backend's pages before recording, or the record PR would
    # leave the published copy one rebuild behind the changelog file.
    _run_py(
        REPO_ROOT / "scripts" / "docs" / "gen_descriptions.py",
        "--changelog-only", "--layer", layer, backend,
    )

    configure_git_identity()
    _git("add", changelog, check=False)
    pages = _changelog_pages(layer, backend)
    for page in pages:
        _git("add", page, check=False)
    commit_msg = f"chore({layer}): record changelog date for {tag} ({backend})"
    # One branch per layer and tag: a dispatch records every backend it pushed
    # onto this one, and it is deleted when its PR merges.
    branch = f"auto/{layer}-changelog-{tag}"
    push_record_branch(branch, commit_msg)
    open_pr(branch, commit_msg, (
        f"The {layer}-image workflow pushed `{tag}` and dated each backend's pending "
        "changelog entry with its registry push_time — the entry that authorized "
        "the rebuild. No image content is changed here; this records that the "
        "rebuilds happened, and why. One dispatch records every backend it pushed "
        "on this branch, so this PR fills up as the matrix proceeds.\n\n"
        "Schema and rules: docs/changelog.md.\n\n"
        f"{DISCLOSURE}"
    ))


# ── app: record the tag into the status matrix, refresh the docs ────────────

# The image tag's plugin suffix is the plugin's PUBLIC version with '+' mapped
# to '_' (image-tag-safe): <version>, or <version>_g<sha7>.d<date> for a
# pre-merge build. Native backends install a labelled wheel but tag the public
# version, so the suffix stays parseable by the drift gate below. Only the temp
# form names a plugin commit — the sha7 after '_g' is the commit the image was
# built from, and it must match what the backend's tracked OPEN upstream PR
# currently points at. Enforced here so a record can never silently pin an image
# whose plugin commit has drifted off the PR head (metax 928bc19 incident,
# 2026-09-03). A tag-form suffix names no sha (the tag is immutable), so there
# is nothing to drift-check and the gate stays quiet.
_PLUGIN_SHA_RE = re.compile(r"(?:^|[._-])g([0-9a-f]{7,40})\.d\d{8}$")


def check_plugin_pin_matches_pr_head(backend_cfg: dict, tag: str) -> str | None:
    """Return an error message if the tag's plugin commit lags an OPEN tracked PR.

    ``prs`` entries in the backend block are upstream PR URLs (the mirror is
    built from their branch head). A tag whose sha is not the current head of
    one of those OPEN PRs is a stale pin — the fix is to rebuild the image from
    the PR head, not to record the old tag.
    """
    prs = backend_cfg.get("prs") or []
    if not prs:
        return None
    m = _PLUGIN_SHA_RE.search(tag)
    if not m:
        return None  # no plugin in the tag; nothing to check
    tag_sha = m.group(1)
    for url in prs:
        pm = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
        if not pm:
            continue
        owner, repo, number = pm.group(1), pm.group(2), pm.group(3)
        try:
            pr = _gh_api("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        except Exception as exc:
            # PR state unavailable — do not block the record on a transient API
            # failure, but say so (the caller sees it in the log).
            print(f"Warning: could not fetch {url} to check pin: {exc}")
            return None
        if pr.get("state") != "open":
            continue
        head = pr.get("head", {}).get("sha", "")
        if not head.lower().startswith(tag_sha.lower()):
            return (
                f"{url} is OPEN but its head is {head[:7]} — the image tag {tag} "
                f"pins plugin commit {tag_sha} (drift). Rebuild the image from the "
                f"PR head, then re-record."
            )
    return None


def component_of(matrix_rel: str) -> str:
    m = re.match(r"packaging/(\w+)/status_matrix\.", matrix_rel)
    if not m:
        sys.exit(f"Error: cannot derive component from matrix path '{matrix_rel}'")
    return m.group(1)


def app_key_of(matrix_rel: str) -> str:
    """Versioned app key from the matrix filename stem (``status_matrix.<app>.yaml``).

    Carries the app version (sglang0.5.18, vllm0.24.0, megatron_training0.17.1)
    so two versions of one app map to distinct records.
    """
    name = Path(matrix_rel).name
    prefix, suffix = "status_matrix.", ".yaml"
    if not (name.startswith(prefix) and name.endswith(suffix)):
        sys.exit(f"Error: cannot derive app key from matrix path '{matrix_rel}'")
    return name[len(prefix):-len(suffix)]


def record_branch(matrix_rel: str, backend: str) -> str:
    """Per-record branch: derived from this record's backend+app.

    Never a shared ``auto/app-image-tag`` — a stale open record PR from an
    unrelated app/backend used to block every later record with rebase
    conflicts (mthreads-musa4.3.6 sglang record, 2026-09-04). Same record
    re-run → same branch, so recovery rebases onto the existing PR.
    """
    return f"auto/app-image-tag-{backend}-{app_key_of(matrix_rel)}"


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


def record_app(matrix_rel: str, backend: str, ref: str, tag: str, changelog: str) -> None:
    matrix_path = REPO_ROOT / matrix_rel
    if not matrix_path.is_file():
        sys.exit(f"Error: matrix file not found: {matrix_rel}")

    # Identity first: the backfill and the docs pipeline below run as flagos-ci
    # too, and subprocesses inherit the environment.
    configure_git_identity()

    # The changelog entry's date is the registry push_time — authoritative and
    # never hand-typed. Backfill it here, where the pushed ref is known, so the
    # same PR carries the matrix record and the dated changelog entry (the gate
    # reads the empty date as "pending", so it must be filled after the push).
    if changelog:
        cl_path = REPO_ROOT / changelog
        if not cl_path.is_file():
            sys.exit(f"Error: changelog not found: {changelog}")
        push_time = harbor_push_time(ref)
        _run_py(REPO_ROOT / "scripts" / "backfill_changelog_date.py",
                str(cl_path), tag, push_time)
    cl_changed = bool(changelog) and _git(
        "diff", "--quiet", changelog, check=False
    ).returncode != 0

    # A stale "未推送" note contradicts image_tag by construction — clear it
    # before the idempotency check so already-recorded backends self-heal.
    changed = clear_stale_note(matrix_path, backend)

    # Idempotency: all three facts already recorded → nothing to do.
    backend_cfg = (yaml.safe_load(matrix_path.read_text()) or {}).get("backends", {}).get(backend, {})
    if (backend_cfg.get("image_tag", "") == tag and backend_cfg.get("launch_docs", False)
            and backend_cfg.get("deps_app", False)):
        if not cl_changed:
            if not changed:
                print(f"{backend} already records image_tag {tag} + launch_docs + deps_app — nothing to do.")
            return

    # Do not record an image whose plugin pin has drifted off a tracked OPEN
    # upstream PR head — rebuild from the PR head first (2026-09-03 incident).
    drift = check_plugin_pin_matches_pr_head(backend_cfg, tag)
    if drift:
        sys.exit(f"Error: {drift}")

    print(f"Recording image_tag {tag} + launch_docs + deps_app for {backend} in {matrix_rel}")

    changed = update_image_tag(matrix_path, backend, tag) or changed
    changed = update_launch_docs(matrix_path, backend) or changed
    changed = update_deps_app(matrix_path, backend) or changed
    if not (changed or cl_changed):
        return

    comp = component_of(matrix_rel)
    branch = record_branch(matrix_rel, backend)

    # Refresh the pipeline so matrix, verification md, and app pages agree.
    # --changelog-only last and unscoped: --app-only has just dropped the
    # Changelog section from *every* app page (they are all re-rendered and all
    # staged here), so all of them have to get it back, not just this one.
    _run_py(REPO_ROOT / "scripts" / "docs" / "gen_data.py")
    _run_py(REPO_ROOT / "scripts" / "render_status_matrix.py", "--component", comp)
    _run_py(REPO_ROOT / "scripts" / "docs" / "gen_descriptions.py", "--app-only")
    _run_py(
        REPO_ROOT / "scripts" / "docs" / "gen_descriptions.py",
        "--changelog-only", "--layer", "app",
    )

    # Stage only the artifacts this record touches.
    patterns = [matrix_rel, "packaging/*/docs/*-verification-matrix.md",
                "docs/content/en/application/*.md", "docs/content/zh-cn/application/*.md",
                "app/*/*.md"]
    if changelog:
        patterns.append(changelog)
    for pattern in patterns:
        _git("add", pattern, check=False)
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("No doc changes after recording tag — nothing to PR.")
        return

    commit_msg = f"chore({comp}): record app image tag {tag} for {backend}"
    push_record_branch(branch, commit_msg)
    open_pr(branch, commit_msg, (
        f"The {comp} app-image workflow pushed an image for `{backend}` and recorded "
        f"the published tag `{tag}` into the status matrix. This PR brings the matrix, the "
        "verification matrix, and the app launch pages back in sync — no functional changes. "
        "Schema and refresh mechanism: docs/status-matrix.md.\n\n"
        f"{DISCLOSURE}"
    ))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--layer", choices=("base", "runtime", "app"), required=True,
        help="which tree the record lands in",
    )
    parser.add_argument(
        "--backend", required=True,
        help="backend key, e.g. hygon-dtk26.04 (the status matrix is keyed by it)",
    )
    parser.add_argument(
        "--tag", required=True,
        help="full pushed image ref; the tag is what follows the last ':'",
    )
    parser.add_argument(
        "--matrix",
        help="app only: status matrix YAML path, relative to the repo root",
    )
    parser.add_argument(
        "--changelog",
        help="app only: per-image changelog YAML (repo-relative); its pending "
        "entry's date is backfilled with the registry push_time",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="base/runtime only: resolve the push time and stop (no writes, no PR)",
    )
    args = parser.parse_args()

    tag = args.tag.rpartition(":")[2]
    if not tag or "/" in tag:
        sys.exit(f"Error: '{args.tag}' carries no tag")

    if args.layer == "app":
        if not args.matrix:
            parser.error("--matrix is required for --layer app")
        if args.dry_run:
            parser.error("--dry-run is not implemented for --layer app")
        record_app(args.matrix, args.backend, args.tag, tag, args.changelog)
        return

    if args.matrix:
        parser.error("--matrix is only meaningful for --layer app")
    if args.changelog:
        parser.error(
            f"--layer {args.layer} records {args.layer}/changelogs/<backend>.yaml; "
            "--changelog is only for --layer app"
        )
    record_changelog(args.layer, args.backend, args.tag, tag, args.dry_run)


if __name__ == "__main__":
    main()
