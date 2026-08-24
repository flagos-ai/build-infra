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

"""Collect pending (⬜) verification cells from the app status matrices.

The verify driver's plan job reads the status matrix YAMLs, collects every ⬜
(待验证) cell, and emits a matrix JSON of {app, backend, compiler, compiler_path,
image, verify_script, verify_args} — one entry per (app, backend, compiler) cell.
A cell is collected at the app's *primary* scenario: the layer its verify
script actually exercises end-to-end (install + import + workload — serve for
vllm, mock-data pretrain for megatron_training) — inference for vllm,
training for megatron_training. megatron_rl is *never* collected: its rl
scenario is upstream-blocked (MLF #116 + flash-attn wheel), so every rl cell
is marked ⛔ and skipped as a terminal symbol. The deeper megatron columns
(post_training / inference) are human/worker conclusions, not script-driven
verifications, so they are never turned into cells.

Every pending (⬜) compiler column becomes a cell — FlagTree (F) and Triton
(T) are each collected when their symbol is ⬜, in F then T order. The driver
passes each cell's compiler to the verify script as ``--compiler
flagtree|triton`` (both verify scripts already take that flag), so each
installed compiler path is exercised explicitly rather than the runtime
default.

Terminal symbols (✅/❌/⛔/？) and "—" (compiler absent on the backend) are
skipped; only ⬜ columns become cells. See docs/verify-orchestrator.md.

Usage:
    python scripts/verify_collect_cells.py                       # all 4 apps
    python scripts/verify_collect_cells.py --app vllm0.20.2      # one app
    python scripts/verify_collect_cells.py --json                # one-line (matrix)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# app -> verify script + the scenario column that script verifies.
# verify_args carries the extra flags the script needs beyond the positional
# backend; the driver appends ``--compiler flagtree|triton`` per cell so each
# installed compiler path is exercised explicitly (F -> flagtree, T -> triton).
APP_VERIFY = {
    "vllm0.20.2": {
        "script": "packaging/vllm/verify-vllm-backend.sh",
        "scenario": "inference",
        "verify_args": "--vllm-version 0.20.2",
    },
    "vllm0.24.0": {
        "script": "packaging/vllm/verify-vllm-backend.sh",
        "scenario": "inference",
        "verify_args": "--vllm-version 0.24.0",
    },
    "megatron_training": {
        "script": "packaging/megatron/verify/verify-megatron-backend.sh",
        "scenario": "training",
        "verify_args": "--scenario training",
    },
    "megatron_rl": {
        "script": "packaging/megatron/verify/verify-megatron-backend.sh",
        "scenario": "rl",
        "verify_args": "--scenario rl",
    },
}

MATRICES = {
    "vllm0.20.2": "packaging/vllm/status_matrix.vllm0.20.2.yaml",
    "vllm0.24.0": "packaging/vllm/status_matrix.vllm0.24.0.yaml",
    "megatron_training": "packaging/megatron/status_matrix.megatron_training.yaml",
    "megatron_rl": "packaging/megatron/status_matrix.megatron_rl.yaml",
}

PENDING = "⬜"

# matrix column (F/T) -> --compiler value the verify scripts accept.
COMPILER_FLAG = {"F": "flagtree", "T": "triton"}


def stack_version() -> str:
    configs = yaml.safe_load((REPO_ROOT / "configs.yaml").read_text())
    return configs["version"]


def runtime_image(backend: str, version: str) -> str:
    return f"harbor.baai.ac.cn/flagos-runtime/flagos-runtime-{backend}:{version}"


def runson_for(backend: str) -> str:
    """JSON-encoded `runs-on` array for the backend (same mapping as
    generate_matrix.py: build-config.yml runners.overrides, else default)."""
    config = yaml.safe_load((REPO_ROOT / ".github" / "build-config.yml").read_text()) or {}
    runners = config.get("runners") or {}
    overrides = runners.get("overrides") or {}
    val = overrides.get(backend, runners.get("default", "ubuntu-latest"))
    if isinstance(val, str):
        val = [val]
    return json.dumps(val)


def _pending_compilers(syms: dict) -> list[str]:
    """Compiler columns still ⬜ for a backend, in F then T order. A column is
    collected only when its symbol is ⬜; "—" (compiler absent on the backend)
    and terminal symbols (✅/❌/⛔/？) are skipped. Both F and T are collected so
    the driver exercises each installed compiler path explicitly."""
    return [c for c in ("F", "T") if syms.get(c) == PENDING]


def collect(app: str, version: str, backends: set[str] | None) -> list[dict]:
    matrix = yaml.safe_load((REPO_ROOT / MATRICES[app]).read_text()) or {}
    meta = APP_VERIFY[app]
    scenario = meta["scenario"]
    verification = matrix.get("scenarios", {}).get(scenario, {}).get("verification", {})
    cells = []
    for backend, syms in verification.items():
        if backends is not None and backend not in backends:
            continue
        for compiler in _pending_compilers(syms):
            cells.append({
                "app": app,
                "backend": backend,
                "vendor": backend.split("-", 1)[0],
                "compiler": compiler,
                "compiler_path": COMPILER_FLAG[compiler],
                "scenario": scenario,
                "image": runtime_image(backend, version),
                "verify_script": meta["script"],
                "verify_args": meta["verify_args"],
                "runson": runson_for(backend),
            })
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", action="append", choices=list(APP_VERIFY),
                        help="collect only this app (repeatable); default all")
    parser.add_argument("--backend", action="append", default=None,
                        help="collect only this backend (repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="emit one-line JSON (GitHub matrix input); default is indented")
    args = parser.parse_args()

    apps = args.app if args.app else list(APP_VERIFY)
    backends = set(args.backend) if args.backend else None
    version = stack_version()
    cells = [cell for app in apps for cell in collect(app, version, backends)]

    out = {"include": cells}
    if args.json:
        print(json.dumps(out))
    else:
        print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
