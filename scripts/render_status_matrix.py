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
per app, and an app name carries no hyphen between app and version
(megatron_training, megatron_rl, vllm0.20.2, vllm0.24.0). Rendered into the
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
import re
import sys
from pathlib import Path

import yaml

# The canonical backend list, in fixed display order (the same order the
# matrices have always used). A status_matrix YAML's backend key must be one
# of these or the renderer errors out.
BACKENDS = [
    "nvidia-cuda12.8",
    "nvidia-cuda13.3",
    "ascend-cann8.5.0",
    "ascend-cann9.0.0",
    "cambricon-neuware4.4.3",
    "cambricon-neuware4.7.2",
    "enflame-tops1.9.10",
    "enflame-tops1.10.6",
    "hygon-dtk26.04",
    "iluvatar-corex4.4.0",
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

# Scenario display order. Matrix columns follow this order across apps — the
# megatron md interleaves the two apps' scenarios (训练, 强化学习, 后训练,
# 推理), the vllm md groups by app version (0.20.2 then 0.24.0).
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
# app is buildable/verified/published on this backend.
FACILITY_BACKEND_ITEMS = (
    ("deps_app", "deps_app 落库"),
    ("launch_docs", "启动文档"),
    ("harbor_repo", "镜像发布"),
)

# Facility boolean → matrix symbol, for the facility checklist's 状态 column.
BOOL_SYMBOL = {True: "✅", False: "⬜"}

# app type key in status_matrix YAML (maps to the matrix scenario family).
APP_TYPES = ("megatron", "vllm")

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
}

# HTML-comment marker blocks that delimit renderer-owned sections in the mds.
_OPEN_RE = re.compile(r"<!--\s*(status-matrix:[^-\s]+(?:-[^\s]+)?)\s*-->")
_CLOSE_RE = re.compile(r"<!--\s*/\s*(status-matrix:[^-\s]+(?:-[^\s]+)?)\s*-->")
VERIFICATION_BLOCK = "status-matrix:verification"


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
        prs = binfo.get("prs")
        if prs is not None and not isinstance(prs, list):
            bad(f"backends.{bkey}.prs: expected a list")
        for pr in prs or []:
            if not isinstance(pr, str):
                bad(f"backends.{bkey}.prs: expected strings, got {pr!r}")

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


def scenario_columns(apps: list[dict]) -> list[tuple[dict, str]]:
    """(app, scenario-id) pairs in matrix column order: global scenario order,
    then app version. Produces the exact megatron column sequence
    (训练/强化学习/后训练/推理) and the vllm sequence (0.20.2 then 0.24.0)."""
    cols = []
    for app in apps:
        for scid in app["scenarios"]:
            cols.append((app, scid))
    cols.sort(key=lambda t: (SCENARIO_ORDER[t[1]], version_key(t[0]["app"])))
    return cols


def matrix_header(cols: list[tuple[dict, str]]) -> list[str]:
    headers = ["厂商", "后端"]
    for app, scid in cols:
        label = app["scenarios"][scid]["label"]
        headers += [f"{label}(T)", f"{label}(F)"]
    return headers


def matrix_rows(cols: list[tuple[dict, str]]) -> list[list[str]]:
    """Verification-matrix rows, one per canonical backend."""
    rows = []
    for bkey in BACKENDS:
        vendor, _ = backend_parts(bkey)
        row = [vendor_display(vendor), backend_display(bkey)]
        for app, scid in cols:
            cell = (app["scenarios"][scid].get("verification") or {}).get(bkey, {})
            row += [cell.get("T", "—"), cell.get("F", "—")]
        rows.append(row)
    return rows


def pr_rows(apps: list[dict]) -> list[list[str]]:
    """Backend-level PR index rows: one per PR, ordered by backend then app."""
    rows = []
    for bkey in BACKENDS:
        for app in apps:
            prs = (app["backends"].get(bkey) or {}).get("prs") or []
            for pr in prs:
                rows.append([vendor_display(backend_parts(bkey)[0]),
                             backend_display(bkey), app["app"], pr])
    return rows


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
    headers = ["后端", "deps_app 落库", "启动文档", "镜像发布"]
    rows = []
    for bkey in BACKENDS:
        if bkey not in app["backends"]:
            continue
        binfo = app["backends"][bkey] or {}
        rows.append([backend_display(bkey)]
                    + [BOOL_SYMBOL[bool(binfo.get(item))]
                       for item, _ in FACILITY_BACKEND_ITEMS])
    lines.append(render_table(headers, rows))
    lines.append("")
    return "\n".join(lines)


def render_verification_block(apps: list[dict]) -> str:
    cols = scenario_columns(apps)
    parts = [render_table(matrix_header(cols), matrix_rows(cols))]
    prs = pr_rows(apps)
    if prs:
        parts += ["", "**后端级上游 PR（验证/镜像基于 PR 分支 Head 的跟踪项）**", ""]
        parts.append(render_table(["厂商", "后端", "App", "PR"], prs))
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
        rewritten = rewrite_block(md_path, VERIFICATION_BLOCK,
                                  render_verification_block(apps))
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
