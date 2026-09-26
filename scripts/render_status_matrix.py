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

"""Re-render app verification-matrix markdown from the status_matrix YAMLs.

Source of truth: packaging/<component>/status_matrix.<app>.yaml — one file
per app, and an app key is the app name + packaged version with no
separator (megatron_training0.17.1, megatron_rl0.17.1, vllm0.20.2,
vllm0.24.0). Rendered into the
adjacent docs file packaging/<component>/docs/<component>-verification-matrix.md
(the megatron md receives all megatron apps' columns; the vllm md receives
both vllm apps' columns).

Each md's renderer-owned sections live between HTML-comment marker blocks.
The renderer rewrites ONLY the marker interiors; hand-written prose around
them (root-cause notes, decisions, verified facts) stays untouched:

    <!-- status-matrix:verification -->      the verification matrix plus a
    ...                                      backend-level PR index
    <!-- /status-matrix:verification -->

    <!-- status-matrix:facility:<app> -->    one per-app facility checklist
    ...                                      (one block per status_matrix YAML)
    <!-- /status-matrix:facility:<app> -->

Adding an app YAML therefore requires adding its facility marker block to
the md first — the renderer errors and lists whatever is missing.

The PR index table's 状态 column is resolved fresh on every render (merge
state changes in the PR's own repo, not build-infra), so regenerating the md
also refreshes upstream PR status. Resolution prefers the GitHub REST API
with GH_TOKEN/GITHUB_TOKEN (every CI step has one, including the record step
on self-hosted runners that carry no `gh` binary), and falls back to the
`gh` CLI for local renders without a token; when neither works the column
falls back to "—" (or, for a recorded row, to the state it already carries).

The YAML and the md do different jobs here. `prs:` is a WORKING SET — the
open tracking items — so a PR leaves the YAML when it merges. The md table
is a RECORD of what each backend's work travelled through, so the renderer
merges the rows already in the md back into the table: it only ever grows,
and a merged row keeps its place with its state refreshed. A `prs:` entry
that is already merged is reported on stderr as one to delete.

Driven from the pre-commit hook (scripts/install-git-hooks.sh) and from CI
(.github/workflows/status-matrix-consistency.yml), which opens a
review-gated fix PR when the committed md drifts from the YAMLs. Schema and
status legend: docs/status-matrix.md.

Usage:
    scripts/render_status_matrix.py                   # regenerate all mds
    scripts/render_status_matrix.py --component vllm  # one component
    scripts/render_status_matrix.py --check           # exit 1 on any drift
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

# The canonical backend list, in fixed display order (the same order the
# matrices have always used). A status_matrix YAML's backend key must be one
# of these or the renderer errors out.
BACKENDS = [
    "nvidia-cuda12.8",
    "nvidia-cuda13.3",
    "ascend-cann8.5.0",
    "ascend-cann8.5.0-910c",
    "ascend-cann9.0.0",
    "ascend-cann9.0.0-910c",
    "cambricon-neuware4.4.3",
    "cambricon-neuware4.7.2",
    "enflame-tops1.9.10",
    "enflame-tops1.10.6",
    "hygon-dtk26.04",
    "iluvatar-corex4.4.0",
    "iluvatar-corex4.5.0",
    "kunlunxin-xre5.37.1",
    "metax-maca3.7.2.1",
    "metax-maca3.8.1.3",
    "mthreads-musa4.3.6",
    "mthreads-musa5.2.0",
    "spacemit-spacemit",
    "sunrise-tangrt1.2.0",
    "thead-ppu2.0.0",
    "tsingmicro-tsm260610",
]

# Chinese vendor display names for the matrix vendor column (same mapping the
# verification matrices have always used).
VENDOR_DISPLAY = {
    "nvidia": "英伟达",
    "ascend": "昇腾",
    "cambricon": "寒武纪",
    "enflame": "燧原",
    "hygon": "海光",
    "iluvatar": "天数智芯",
    "kunlunxin": "昆仑芯",
    "metax": "沐曦",
    "mthreads": "摩尔线程",
    "spacemit": "进迭时空",
    "sunrise": "曦望",
    "thead": "平头哥",
    "tsingmicro": "清微智能",
}

# Legend text lives in the mds' own 状态图例 section (outside the marker
# blocks), so it stays single-authored with the rest of the human prose.

# Scenario display order. Matrix columns follow this order within an app:
# megatron scenarios order as 训练, 强化学习, 后训练, 推理.
SCENARIO_ORDER = {
    "training": 0,
    "rl": 1,
    "post_training": 2,
    "inference": 3,
}

# Per-app facility items, shared across all backends of that app. These are
# build-infra's own engineering artifacts — app-level, not backend-level.
FACILITY_APP_ITEMS = (
    ("containerfile", "Containerfile"),
    ("workflow", "构建 workflow"),
)

# Per-backend facility items, the checklist the user asked for: whether the
# app is buildable/verified on this backend. 镜像发布 is a derived column, not
# a stored boolean — a backend is published iff it carries an `image_tag`
# (single source of truth, no separate field to drift).
FACILITY_BACKEND_ITEMS = (
    ("deps_app", "deps_app 落库"),
    ("launch_docs", "启动文档"),
)

# Facility boolean → matrix symbol, for the facility checklist's 状态 column.
BOOL_SYMBOL = {True: "✅", False: "⬜"}

# app type key in status_matrix YAML (maps to the matrix scenario family).
APP_TYPES = ("megatron", "vllm", "sglang")

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = {
    "megatron": {
        "yaml_dir": REPO_ROOT / "packaging" / "megatron",
        "md": REPO_ROOT / "packaging" / "megatron" / "docs" / "megatron-verification-matrix.md",
    },
    "vllm": {
        "yaml_dir": REPO_ROOT / "packaging" / "vllm",
        "md": REPO_ROOT / "packaging" / "vllm" / "docs" / "vllm-verification-matrix.md",
    },
    "sglang": {
        "yaml_dir": REPO_ROOT / "packaging" / "sglang",
        "md": REPO_ROOT / "packaging" / "sglang" / "docs" / "sglang-verification-matrix.md",
    },
}

# HTML-comment marker blocks that delimit renderer-owned sections in the mds.
_OPEN_RE = re.compile(r"<!--\s*(status-matrix:[^-\s]+(?:-[^\s]+)?)\s*-->")
_CLOSE_RE = re.compile(r"<!--\s*/\s*(status-matrix:[^-\s]+(?:-[^\s]+)?)\s*-->")
VERIFICATION_BLOCK = "status-matrix:verification"

# Registration rule for upstream PRs: prs: entries must be full pull URLs so
# the tracking table is unambiguous about repo and number (bare #N is not
# tracked). Enforced here so no naked number can re-enter the YAMLs.
_PR_URL_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+$")

# `gh pr view --json state` values → display. Merged PRs report MERGED.
PR_STATE = {"MERGED": "已合并", "OPEN": "OPEN", "CLOSED": "已关闭"}

# Shape of one PR index row in the md. Matched by shape rather than by table
# position so the block's heading text can change without dropping the record.
_PR_ROW_RE = re.compile(
    r"^\|\s*(?P<vendor>[^|]+?)\s*\|\s*(?P<backend>[^|]+?)\s*\|"
    r"\s*(?P<app>[^|]+?)\s*\|\s*(?P<pr>https://github\.com/\S+?)\s*\|"
    r"\s*(?P<state>[^|]+?)\s*\|\s*$"
)


def backend_parts(key: str) -> tuple[str, str]:
    vendor, _, backend = key.partition("-")
    return vendor, backend


def backend_display(key: str) -> str:
    """Display form of a {vendor}-{backend} key: 'cuda12.8' -> 'CUDA 12.8'."""
    _, backend = backend_parts(key)
    m = re.match(r"([a-z]+)(\d.*)?$", backend)
    head, tail = (m.group(1).upper(), m.group(2)) if m else (backend.upper(), None)
    return f"{head} {tail}" if tail else head


def vendor_display(vendor: str) -> str:
    if vendor in VENDOR_DISPLAY:
        return VENDOR_DISPLAY[vendor]
    return backend_display(f"{vendor}-{vendor}")  # fallback, mirrors launch docs


# Display form → backend key, so a row read back from the md can be ordered
# among the rows the YAML produces.
_BACKEND_RANK = {key: i for i, key in enumerate(BACKENDS)}
_BACKEND_KEY_BY_DISPLAY = {
    (vendor_display(backend_parts(key)[0]), backend_display(key)): key
    for key in BACKENDS
}


def version_key(version: str) -> tuple:
    parts = []
    for tok in version.split("."):
        parts.append(int(tok) if tok.isdigit() else tok)
    return tuple(parts)


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        sys.exit(f"render_status_matrix: {path} is not a mapping")
    return data


def validate_app(data: dict, path: Path, comp_md: Path) -> None:
    """Validate one status_matrix YAML, exiting with a message on error."""
    problems = []

    def bad(msg: str):
        problems.append(f"{path}: {msg}")

    if data.get("type") not in APP_TYPES:
        bad(f"type must be one of {APP_TYPES}, got {data.get('type')!r}")
    if not isinstance(data.get("app"), str) or not data["app"]:
        bad("app: required non-empty string")
    if not isinstance(data.get("description"), str):
        bad("description: required string")
    if not isinstance(data.get("last_updated"), str):
        bad("last_updated: required date string (YYYY-MM-DD)")

    comp = Path(comp_md).name.removesuffix("-verification-matrix.md")
    if data.get("type") == "megatron" and comp != "megatron":
        bad(f"type megatron renders into megatron-verification-matrix.md, not {comp}")
    if data.get("type") == "vllm" and comp != "vllm":
        bad(f"type vllm renders into vllm-verification-matrix.md, not {comp}")
    if data.get("type") == "sglang" and comp != "sglang":
        bad(f"type sglang renders into sglang-verification-matrix.md, not {comp}")

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        bad("scenarios: required non-empty mapping")
    for sid, sc in scenarios.items():
        if sid not in SCENARIO_ORDER:
            bad(f"scenarios: unknown scenario {sid!r}")
        if not isinstance(sc, dict) or not isinstance(sc.get("label"), str):
            bad(f"scenarios.{sid}: label: required string")
        for bkey, cell in (sc.get("verification") or {}).items():
            if bkey not in BACKENDS:
                bad(f"scenarios.{sid}.verification: unknown backend {bkey!r}")
            if not isinstance(cell, dict):
                bad(f"scenarios.{sid}.verification.{bkey}: expected a {{T, F}} map")
                continue
            for comp_key in ("T", "F"):
                if comp_key not in cell or not isinstance(cell[comp_key], str):
                    bad(f"scenarios.{sid}.verification.{bkey}: {comp_key} required")

    backends = data.get("backends")
    if not isinstance(backends, dict):
        bad("backends: required mapping")
    for bkey, binfo in backends.items():
        if bkey not in BACKENDS:
            bad(f"backends: unknown backend {bkey!r}")
        if binfo is None:
            continue
        if not isinstance(binfo, dict):
            bad(f"backends.{bkey}: expected a mapping")
            continue
        for item in FACILITY_BACKEND_ITEMS:
            if item[0] not in binfo:
                bad(f"backends.{bkey}: missing facility item {item[0]!r}")
        tag = binfo.get("image_tag")
        if tag is not None and (not isinstance(tag, str) or not tag):
            bad(f"backends.{bkey}.image_tag: expected a non-empty string")
        prs = binfo.get("prs")
        if prs is not None and not isinstance(prs, list):
            bad(f"backends.{bkey}.prs: expected a list")
        for pr in prs or []:
            if not isinstance(pr, str):
                bad(f"backends.{bkey}.prs: expected strings, got {pr!r}")
            elif not _PR_URL_RE.match(pr):
                bad(f"backends.{bkey}.prs: {pr!r} is not a GitHub PR URL — "
                    f"register the full link, bare #N is not tracked")
        note = binfo.get("note")
        if note is not None and (not isinstance(note, str) or not note):
            bad(f"backends.{bkey}.note: expected a non-empty string")

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        sys.exit(1)


def load_apps(comp: str) -> list[dict]:
    """Load + validate all status_matrix YAMLs of a component, in render order."""
    yaml_dir = COMPONENTS[comp]["yaml_dir"]
    files = sorted(yaml_dir.glob("status_matrix.*.yaml"))
    apps = [load_yaml(p) for p in files]
    for data, p in zip(apps, files):
        validate_app(data, p, COMPONENTS[comp]["md"])

    def sort_key(a: dict):
        order = min(SCENARIO_ORDER[s] for s in a["scenarios"])
        return (order, version_key(a["app"]))

    return sorted(apps, key=sort_key)


def scenario_columns(apps: list[dict]) -> list[list[tuple[dict, str]]]:
    """Column groups, one list per table — one group per app, sorted by
    version. Each app version renders as its own table: 0.17.1 and 0.18.2
    (and vllm's 0.20.2 / 0.24.0) are not mixed into shared columns."""
    groups = []
    for app in sorted(apps, key=lambda a: version_key(a["app"])):
        cols = [(app, scid) for scid in app["scenarios"]]
        groups.append((cols, app))
    return groups


def matrix_header(cols: list[tuple[dict, str]]) -> list[str]:
    headers = ["厂商", "后端"]
    for app, scid in cols:
        label = app["scenarios"][scid]["label"]
        headers += [f"{label}(T)", f"{label}(F)"]
    return headers


def matrix_rows(cols: list[tuple[dict, str]]) -> list[list[str]]:
    """Verification-matrix rows: the backends the component's app lines have
    been opened on, in canonical display order. BACKENDS fixes the order
    only — a backend no app line declares gets no row at all rather than an
    all-"—" one (an app line not opened on 910C is not "backend has no such
    compiler")."""
    declared = set()
    for app, _ in cols:
        declared |= set(app["backends"])
        for sc in app["scenarios"].values():
            declared |= set(sc.get("verification") or {})
    rows = []
    for bkey in BACKENDS:
        if bkey not in declared:
            continue
        vendor, _ = backend_parts(bkey)
        row = [vendor_display(vendor), backend_display(bkey)]
        for app, scid in cols:
            cell = (app["scenarios"][scid].get("verification") or {}).get(bkey, {})
            row += [cell.get("T", "—"), cell.get("F", "—")]
        rows.append(row)
    return rows


def collect_pr_urls(apps: list[dict]) -> list[str]:
    """All backend PR URLs of a component, for one batched state lookup."""
    urls = []
    for app in apps:
        for binfo in app["backends"].values():
            urls += (binfo or {}).get("prs") or []
    return urls


def _rest_pr_state(url: str) -> str | None:
    """PR merge state via the REST API; None when no token or the call fails.

    The record workflow's step runs on self-hosted runners that carry no
    `gh` binary, so resolving states must not depend on the CLI — every such
    runner does have GITHUB_TOKEN, and the matrix lists same-org public PRs
    whose read scope the token covers.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    path = url.split("github.com/", 1)[-1]  # owner/repo/pull/N
    owner_repo, _, num = path.rpartition("/pull/")
    if not owner_repo or not num.isdigit():
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{owner_repo}/pulls/{num}", method="GET"
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except OSError:
        return None
    # REST reports state lowercase ("open"/"closed"), and a merged PR comes
    # back "closed" with merged_at set. Normalize to the gh CLI scheme
    # ("OPEN"/"CLOSED"/"MERGED") so PR_STATE applies to both resolution
    # paths — feeding raw REST state through it rendered every row "—".
    if data.get("merged_at"):
        return "MERGED"
    return (data.get("state") or "").upper() or None


def resolve_pr_states(urls: list[str]) -> dict[str, str]:
    """Best-effort {url: 已合并|OPEN|已关闭} for the URLs it could resolve.

    Merge state changes in the PR's own repo, not build-infra, so it cannot
    be maintained in YAML — resolve it fresh on every render. Resolution
    order: REST with a workflow token (deterministic across runners, `gh`
    binary or not), then the `gh` CLI (tokenless local renders). An
    unresolvable URL is simply absent from the map, not "—": callers decide
    what an unknown state means for the cell they are filling.
    """
    states: dict[str, str] = {}
    failures = 0
    for url in sorted(set(urls)):
        state = _rest_pr_state(url)
        if state is None:
            try:
                out = subprocess.run(
                    ["gh", "pr", "view", url, "--json", "state"],
                    capture_output=True, text=True, timeout=15,
                )
                if out.returncode == 0:
                    state = json.loads(out.stdout).get("state")
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                state = None
        if state is not None:
            states[url] = PR_STATE.get(state, "—")
        else:
            failures += 1
    if failures:
        print(f"render_status_matrix: {failures} 个 PR 状态查询失败，状态列显示 —"
              f"（渲染需在可访问 GitHub 的环境执行）", file=sys.stderr)
    return states


def parse_recorded_pr_rows(block: str) -> list[list[str]]:
    """The PR index rows already in the md — the record the render preserves."""
    rows = []
    for line in block.splitlines():
        m = _PR_ROW_RE.match(line)
        if m:
            rows.append([m.group("vendor"), m.group("backend"),
                         m.group("app"), m.group("pr"), m.group("state")])
    return rows


def pr_rows(apps: list[dict], states: dict[str, str] | None = None,
            recorded: list[list[str]] | None = None) -> list[list[str]]:
    """Backend-level PR index rows: one per PR, ordered by backend then app.

    `prs:` is the working set and drops a PR as soon as it merges, so the rows
    already in the md are merged back in: the table is a record of what each
    backend's work travelled through and only ever grows. A recorded row is
    kept verbatim (the YAML no longer knows which backend/app it belonged to),
    keeping its own state when this render could not resolve one.

    Deduplication is per (backend, app, PR): one PR is routinely tracked by
    several backends, and each of those is its own row.
    """
    states = states or {}
    rows: list[list[str]] = []
    seq = 0
    seen: set[tuple[str, str, str]] = set()
    for bkey in BACKENDS:
        for app in apps:
            for pr in (app["backends"].get(bkey) or {}).get("prs") or []:
                key = (backend_display(bkey), app["app"], pr)
                if key in seen:
                    continue
                seen.add(key)
                rows.append([seq, vendor_display(backend_parts(bkey)[0]),
                             backend_display(bkey), app["app"], pr,
                             states.get(pr, "—")])
                seq += 1
    for row in recorded or []:
        if len(row) < 5 or (row[1], row[2], row[3]) in seen:
            continue
        seen.add((row[1], row[2], row[3]))
        rows.append([seq, row[0], row[1], row[2], row[3],
                     states.get(row[3], row[4])])
        seq += 1
    app_rank = {app["app"]: i for i, app in enumerate(apps)}
    rows.sort(key=lambda r: (
        _BACKEND_RANK.get(_BACKEND_KEY_BY_DISPLAY.get((r[1], r[2])), len(BACKENDS)),
        app_rank.get(r[3], len(app_rank)),
        r[0],
    ))
    return [row[1:] for row in rows]


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "---|" * len(headers))
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def render_facility(app: dict, apps: list[dict]) -> str:
    """Facility checklist for one app: shared app-level items, then one row per
    backend with the per-backend booleans and any backend-level PRs."""
    lines = [f"### {app['app']}", ""]
    lines.append("> 数据截止：" + app["last_updated"])
    lines.append("")
    lines.append("**App 级设施（全后端共享）**")
    lines.append("")
    headers = ["事项", "状态"]
    rows = []
    for item, label in FACILITY_APP_ITEMS:
        rows.append([label, BOOL_SYMBOL[bool(app["facility"].get(item))]])
    lines.append(render_table(headers, rows))
    lines.append("")
    lines.append("**后端级设施**")
    lines.append("")
    headers = ["后端"] + [label for _, label in FACILITY_BACKEND_ITEMS] + ["镜像发布", "备注"]
    rows = []
    for bkey in BACKENDS:
        if bkey not in app["backends"]:
            continue
        binfo = app["backends"][bkey] or {}
        row = [backend_display(bkey)]
        row += [BOOL_SYMBOL[bool(binfo.get(item))]
                for item, _ in FACILITY_BACKEND_ITEMS]
        row.append(BOOL_SYMBOL[bool(binfo.get("image_tag"))])
        row.append(binfo.get("note") or "—")
        rows.append(row)
    lines.append(render_table(headers, rows))
    lines.append("")
    return "\n".join(lines)


def render_verification_block(apps: list[dict],
                              recorded: list[list[str]] | None = None) -> str:
    groups = scenario_columns(apps)
    parts: list[str] = []
    for i, (cols, app) in enumerate(groups):
        if i:
            parts.append("")
        # Each app version renders as its own table; give it a heading so a
        # reader can tell which version a table belongs to (the table's own
        # column labels repeat across versions). Heading level #### keeps
        # clear of the facility blocks' ### per-app headings.
        parts.append(f"#### {app['app']}")
        parts.append("")
        parts.append(render_table(matrix_header(cols), matrix_rows(cols)))
    tracked = collect_pr_urls(apps)
    states = resolve_pr_states(tracked + [row[3] for row in recorded or []])
    merged = sorted({u for u in tracked if states.get(u) == PR_STATE["MERGED"]})
    if merged:
        # The YAML is a working set of open items; a merged one belongs in the
        # md record only. Reported, not enforced — the render still succeeds.
        print(f"render_status_matrix: {len(merged)} 个已合并的 PR 仍在 YAML 的 prs: "
              f"里，合并后应删除该条目（md 中的记录保留）：", file=sys.stderr)
        for url in merged:
            print(f"  {url}", file=sys.stderr)
    prs = pr_rows(apps, states, recorded)
    if prs:
        parts += ["", "**后端级上游 PR（验证/镜像基于 PR 分支 Head 的跟踪项）**", ""]
        parts.append(render_table(["厂商", "后端", "App", "PR", "状态"], prs))
    return "\n".join(parts)


def render_facility_block(app: dict, apps: list[dict]) -> str:
    return render_facility(app, apps)


def find_markers(text: str, name: str) -> tuple[int, int] | None:
    """Return (start, end) of the block named `name`, or None if not present."""
    opened, closed = [], []
    for m in _OPEN_RE.finditer(text):
        if m.group(1) == name:
            opened.append(m)
    for m in _CLOSE_RE.finditer(text):
        if m.group(1) == name:
            closed.append(m)
    if not opened or not closed:
        return None
    if len(opened) > 1 or len(closed) > 1:
        sys.exit(f"render_status_matrix: block {name!r} appears more than once in "
                 f"the md — move the markers so each renderer-owned block is unique")
    return opened[0].end(), closed[0].start()


def rewrite_block(md_path: Path, name: str, content: str) -> bool:
    """Rewrite one marker block in place. Returns True if the file changed."""
    md = md_path.read_text()
    span = find_markers(md, name)
    if span is None:
        sys.exit(f"render_status_matrix: marker block {name!r} not found in "
                 f"{md_path}\nadd:\n"
                 f"    <!-- {name} -->\n    ...\n    <!-- /{name} -->")
    start, end = span
    updated = md[:start].rstrip() + "\n\n" + content + "\n\n" + md[end:].lstrip()
    if updated == md:
        return False
    md_path.write_text(updated)
    return True


def render_component(comp: str) -> list[str]:
    """Render one component's md. Returns the paths that were rewritten."""
    apps = load_apps(comp)
    changed = []
    for md_path in [COMPONENTS[comp]["md"]]:
        md = md_path.read_text()
        span = find_markers(md, VERIFICATION_BLOCK)
        recorded = parse_recorded_pr_rows(md[span[0]:span[1]]) if span else []
        rewritten = rewrite_block(md_path, VERIFICATION_BLOCK,
                                  render_verification_block(apps, recorded))
        if rewritten:
            changed.append(str(md_path))
    for app in apps:
        block = f"status-matrix:facility:{app['app']}"
        rewritten = rewrite_block(COMPONENTS[comp]["md"], block,
                                  render_facility_block(app, apps))
        if rewritten:
            changed.append(str(COMPONENTS[comp]["md"]))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-render app verification-matrix markdown from "
                    "status_matrix YAMLs")
    parser.add_argument("--component", choices=sorted(COMPONENTS),
                        help="render only this component's md")
    parser.add_argument("--check", action="store_true",
                        help="fail (exit 1) if any md would change")
    args = parser.parse_args()

    components = [args.component] if args.component else list(COMPONENTS)
    changed = []
    for comp in components:
        changed.extend(render_component(comp))

    if args.check and changed:
        print("render_status_matrix: stale verification matrix — run "
              "scripts/render_status_matrix.py and commit the result", file=sys.stderr)
        for p in sorted(set(changed)):
            print(f"  {p}", file=sys.stderr)
        return 1
    for p in sorted(set(changed)):
        print(f"render_status_matrix: updated {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
