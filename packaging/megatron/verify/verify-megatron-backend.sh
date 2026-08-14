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
# verify-megatron-backend.sh — Install and verify megatron-core on a backend
# ============================================================
#
# Install the megatron-core wheel into a `flagos-runtime-{vendor}-{backend}`
# container and prove the install is inert — i.e. the carefully crafted
# torch/triton/flag_gems/numpy matrix is unchanged after the single-step
# install, and megatron.core actually loads. The wheel keeps its
# `torch>=2.6.0` Requires-Dist; the runtime's vendor torch satisfies it, so
# pip downloads and overwrites nothing.
#
# Usage:
#   ./verify-megatron-backend.sh <vendor-backend> [--megatron-version <ver>]
#
# Examples:
#   ./verify-megatron-backend.sh hygon-dtk26.04
#   ./verify-megatron-backend.sh hygon-dtk26.04 --megatron-version 0.17.1
#
# Prerequisites:
#   - Running on the target node with hardware access
#   - megatron-core wheel (built by packaging/megatron/builder/, same Python
#     version as the backend runtime) uploaded to the vendor PyPI
#     (flagos-pypi-<vendor>)
#
# Steps:
#   1. Start runtime container with hardware access (build-config.yml run flags)
#   2. BEFORE snapshot: torch / triton / flag_gems / numpy (+ site-package path)
#   3. Single-step install (no --no-deps) of megatron-core
#   4. AFTER snapshot: compare each package version to BEFORE — must be equal
#      item by item, or the install corrupted the matrix (fail)
#   5. Import check: source the vendor env if needed, then import
#      megatron.core and confirm helpers_cpp is bound

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

MEGATRON_VERSION="${MEGATRON_VERSION:-0.17.1}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --megatron-version) MEGATRON_VERSION="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 <vendor-backend> [--megatron-version <ver>]"
            exit 0
            ;;
        *) break ;;
    esac
done

VENDOR_BACKEND="${1:-}"
if [[ -z "$VENDOR_BACKEND" ]]; then
    echo "Error: vendor-backend argument required" >&2
    exit 1
fi
VENDOR="${VENDOR_BACKEND%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

# ── Configuration ───────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate the repo root: walk up from SCRIPT_DIR until configs.yaml is found.
REPO_ROOT=""
d="${SCRIPT_DIR}"
while [[ "$d" != "/" ]]; do
    if [[ -f "$d/configs.yaml" ]]; then REPO_ROOT="$d"; break; fi
    d="$(dirname "$d")"
done
if [[ -z "$REPO_ROOT" ]]; then
    echo "Error: configs.yaml not found (searched up from ${SCRIPT_DIR})" >&2
    exit 1
fi

STACK_VERSION=$(python3 -c "
import yaml
with open('${REPO_ROOT}/configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")

RUNTIME_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR_BACKEND}:${STACK_VERSION}"
VENDOR_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/simple"
ALIYUN_PYPI="https://mirrors.aliyun.com/pypi/simple"
CONTAINER="megatron-verify-${VENDOR}-${BACKEND}"
WORK_DIR="/tmp/megatron-verify-${VENDOR}-${BACKEND}-$$"

# Packages that must survive the install bit-for-bit.
WATCH_PKGS="torch triton flag_gems numpy"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $*"; }

# ── Print header ────────────────────────────────────────────────────────

echo "========================================"
echo "Megatron Backend Verification"
echo "========================================"
echo "Vendor-Backend:    ${VENDOR_BACKEND}"
echo "Runtime Image:     ${RUNTIME_IMAGE}"
echo "Megatron Version:  ${MEGATRON_VERSION}"
echo ""

# ── Cleanup function ────────────────────────────────────────────────────

cleanup() {
    echo ""
    log_info "Cleaning up container..."
    docker rm -f "${CONTAINER}" 2>/dev/null || true
    rm -rf "${WORK_DIR}" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: Start runtime container with hardware access ────────────────

log_step "Step 1: Starting runtime container"

mkdir -p "${WORK_DIR}"
docker rm -f "${CONTAINER}" 2>/dev/null || true

# Read device flags from build-config.yml (toolkit preferred over raw).
RUN_FLAGS=$(python3 -c "
import yaml
vendor = '${VENDOR}'
with open('${REPO_ROOT}/.github/build-config.yml') as f:
    config = yaml.safe_load(f)
vendor_config = config.get('run', {}).get('vendors', {}).get(vendor, {})
print(vendor_config.get('toolkit', '') or vendor_config.get('raw', ''))
")

docker run -d --name "${CONTAINER}" \
    ${RUN_FLAGS} \
    --network host \
    "${RUNTIME_IMAGE}" \
    sleep infinity

log_info "Container started: ${CONTAINER}"

# ── Snapshot helpers ────────────────────────────────────────────────────

# Emits "<pkg> <version> <location>" per watched package; missing package =>
# "<pkg> MISSING". The vendor SDK env may be needed before import (hygon:
# source /opt/dtk-26.04/env.sh for LD_LIBRARY_PATH); the runtime image bakes
# it for bash-invoked commands, so the source is defensive only.
snapshot() {
    docker exec "${CONTAINER}" bash -c '
        source /opt/dtk-26.04/env.sh 2>/dev/null || true
        for pkg in '"${WATCH_PKGS}"'; do
            # No f-string with embedded backslash: runtime pythons are 3.10/3.11,
            # where that is a SyntaxError (PEP 701 only in 3.12+).
            python3 - "$pkg" <<'"'"'PY'"'"'
import sys, importlib.metadata as m
pkg = sys.argv[1]
try:
    dist = m.distribution(pkg)
    print(pkg, dist.version, dist.locate_file(""))
except m.PackageNotFoundError:
    print(pkg, "MISSING")
PY
        done
    '
}

# ── Step 2: BEFORE snapshot ─────────────────────────────────────────────

log_step "Step 2: BEFORE dependency snapshot"

snapshot | tee "${WORK_DIR}/before.txt"

# ── Step 3: Single-step install (no --no-deps) ──────────────────────────

log_step "Step 3: Installing megatron-core==${MEGATRON_VERSION}"

docker exec "${CONTAINER}" bash -c "
    pip install \
        --index-url '${VENDOR_PYPI}' \
        --extra-index-url '${ALIYUN_PYPI}' \
        'megatron-core==${MEGATRON_VERSION}'
"

log_info "megatron-core installed:"
docker exec "${CONTAINER}" pip show megatron-core | grep -E "^(Name|Version|Location)" || true

# ── Step 4: AFTER snapshot and compare ──────────────────────────────────

log_step "Step 4: AFTER dependency snapshot"

snapshot | tee "${WORK_DIR}/after.txt"

log_step "Step 4b: Comparing BEFORE vs AFTER"

FAILED=0
while read -r line; do
    pkg="${line%% *}"
    before="${line}"
    after="$(grep -F "${pkg} " "${WORK_DIR}/after.txt" || true)"
    if [[ "${before}" != "${after}" ]]; then
        log_error "Matrix corrupted for ${pkg}:"
        echo "    before: ${before}"
        echo "    after:  ${after}"
        FAILED=1
    else
        log_info "unchanged: ${before}"
    fi
done < "${WORK_DIR}/before.txt"

if [[ "${FAILED}" == 1 ]]; then
    log_error "Dependency matrix changed — install was NOT inert. Aborting." >&2
    exit 1
fi
log_info "Dependency matrix intact: torch / triton / flag_gems / numpy unchanged."

# ── Step 5: Import check ────────────────────────────────────────────────

log_step "Step 5: Import check (megatron.core + helpers_cpp)"

docker exec "${CONTAINER}" bash -c '
    source /opt/dtk-26.04/env.sh 2>/dev/null || true
    python3 - <<'"'"'PY'"'"'
import importlib.metadata
import megatron.core

print("megatron.core imported:", megatron.core.__file__)
print("megatron-core version:", importlib.metadata.version("megatron-core"))

# helpers_cpp is the compiled extension; importing it proves the .so is
# present and its pybind11 init binds against the runtime pybind11.
from megatron.core.datasets import helpers_cpp
print("helpers_cpp:", helpers_cpp.__file__)
assert callable(helpers_cpp.build_sample_idx_int32)
assert callable(helpers_cpp.build_sample_idx_int64)
assert callable(helpers_cpp.build_exhaustive_blending_indices)
print("helpers_cpp bindings OK")
PY
'

# ── Summary ─────────────────────────────────────────────────────────────

echo ""
echo "========================================"
echo "Verification Summary"
echo "========================================"
echo "Backend:          ${VENDOR_BACKEND}"
echo "Megatron Version: ${MEGATRON_VERSION}"
echo "Container:        ${CONTAINER}"
echo ""
echo "To debug:"
echo "  docker exec -it ${CONTAINER} bash"
echo ""
