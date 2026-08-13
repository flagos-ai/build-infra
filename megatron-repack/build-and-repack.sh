#!/usr/bin/env bash
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

# ============================================================
# build-and-repack.sh — Repack a megatron-core wheel for one backend
# ============================================================
#
# STUB — to be filled during the hygon25 verification phase.
#
# Facility 1 (megatron-builder/) produces the cp310/cp311/cp312 wheels;
# this script consumes one of them and applies the dependency surgery
# (megatron-repack/config.yaml) so a single-step `pip install` can never
# disturb the runtime image's torch/triton/flag_gems matrix.
#
# Usage (intended):
#   build-and-repack.sh hygon-dtk26.04 /path/to/megatron_core-0.17.1-cp310-cp310-linux_x86_64.whl
#   build-and-repack.sh nvidia-cuda12.8 /path/to/megatron_core-0.17.1-cp312-...whl --upload
#
# Options (intended):
#   --upload   twine-upload the repacked +flagos wheels to the per-vendor
#              PyPI (flagos-pypi-<vendor>). Opt-in — publishing is outward
#              facing, so it never runs by default.
#
# Prerequisites (intended):
#   - Facility-1 wheel (from megatron-builder/) for the backend's Python
#   - python3 + pyyaml on the host (for reading configs.yaml)
#   - ../vllm-repack/repack.py — REUSED read-only, never copied or modified
#   - twine on the host (only when --upload is used)

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <vendor>-<backend> <wheel> [--upload]" >&2
    exit 1
fi

VENDOR_BACKEND="$1"
WHEEL="$2"
shift 2

UPLOAD=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --upload) UPLOAD=true; shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

VENDOR="${VENDOR_BACKEND%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

# ── Paths ───────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/megatron-repack-${VENDOR}-${BACKEND}"

# ── TODO: fill during verification ─────────────────────────────────────
# 1. Resolve STACK_VERSION from ${SCRIPT_DIR}/../configs.yaml.
# 2. Copy the Facility-1 wheel + config.yaml + (read-only) repack.py into
#    WORK_DIR, run:
#      python3 ${WORK_DIR}/repack.py --config ${WORK_DIR}/config.yaml ${WORK_DIR}/input/megatron_core-*.whl
#    → produces megatron_core-0.17.1+flagos-...whl in WORK_DIR/output/.
# 3. Sanity-gate the repacked wheel: METADATA no longer contains
#    `Requires-Dist: torch`, `+flagos` suffix present, .deps-manifest.yaml
#    written.
# 4. Upload (opt-in): twine upload --repository-url
#    "https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/" \
#    ${WORK_DIR}/output/*.whl
# 5. Report the removed/retained dependency manifest.

echo "STUB: repack pipeline for ${VENDOR_BACKEND} not implemented yet." >&2
echo "      Wheel:  ${WHEEL}" >&2
echo "      See report-megatron-0.17.1.md §2.2 for the design." >&2
exit 1
