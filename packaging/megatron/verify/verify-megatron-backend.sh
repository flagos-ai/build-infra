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
# Two modes:
#   default:       install the wheel into a fresh runtime container, then
#                  compare before/after snapshots — proves the install itself
#                  is inert (the app Containerfile's build step replay).
#   --app-image:   the app image was built FROM the runtime image with the
#                  single-step install baked in. Snapshot the runtime image as
#                  BEFORE and the built app image as AFTER: an equal matrix
#                  proves the app-image build left the runtime packages
#                  untouched, and the import check runs on the actual artifact.
#                  No pip install (it already happened at image build time).
#
# Usage:
#   ./verify-megatron-backend.sh <vendor-backend> [--megatron-version <ver>] [--app-image <tag>]
#
# Examples:
#   ./verify-megatron-backend.sh hygon-dtk26.04
#   ./verify-megatron-backend.sh hygon-dtk26.04 --megatron-version 0.17.1
#   ./verify-megatron-backend.sh hygon-dtk26.04 \
#       --app-image harbor.baai.ac.cn/flagos-app/megatron-hygon-dtk26.04:2.1.2
#
# Prerequisites:
#   - Running on the target node with hardware access
#   - megatron-core wheel (built by packaging/megatron/builder/, same Python
#     version as the backend runtime) uploaded to the vendor PyPI
#     (flagos-pypi-<vendor>) — only for default mode
#   - --app-image mode: the app image tag must exist locally (docker build)
#
# Steps:
#   1. Start runtime container with hardware access (build-config.yml run flags);
#      with --app-image also start the app image container
#   2. BEFORE snapshot: torch / triton / flag_gems / numpy (+ site-package path)
#   3. Default mode: single-step install (no --no-deps) of megatron-core.
#      App-image mode: skipped (install baked at image build time)
#   4. AFTER snapshot: compare each package version to BEFORE — must be equal
#      item by item, or the install corrupted the matrix (fail)
#   5. Import check: import megatron.core and confirm helpers_cpp is bound
#      (the vendor env comes from the image itself via BASH_ENV → profile.d)

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

MEGATRON_VERSION="${MEGATRON_VERSION:-0.17.1}"
APP_IMAGE="${APP_IMAGE:-}"
COMPILER=""

POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --megatron-version) MEGATRON_VERSION="$2"; shift 2 ;;
        --app-image) APP_IMAGE="$2"; shift 2 ;;
        --compiler) COMPILER="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 <vendor-backend> [--megatron-version <ver>] [--app-image <tag>] [--compiler <c>]"
            echo "  --compiler <c>   Compiler path to verify: flagtree | triton (default: runtime default)"
            exit 0
            ;;
        # Not an option: positional. Collect (don't break) so options may
        # appear before OR after the vendor-backend argument.
        *) POSITIONAL_ARGS+=("$1"); shift ;;
    esac
done

VENDOR_BACKEND="${POSITIONAL_ARGS[0]:-}"
if [[ -z "$VENDOR_BACKEND" ]]; then
    echo "Error: vendor-backend argument required" >&2
    exit 1
fi
VENDOR="${VENDOR_BACKEND%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

if [[ -n "$COMPILER" && "$COMPILER" != "flagtree" && "$COMPILER" != "triton" ]]; then
    echo "Error: --compiler must be 'flagtree' or 'triton' (got '$COMPILER')" >&2
    exit 1
fi

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
APP_CONTAINER="megatron-verify-${VENDOR}-${BACKEND}-app"
# Which container the AFTER snapshot + import check run against: the app image
# container in --app-image mode, the same (installed) container otherwise.
AFTER_CONTAINER="${CONTAINER}"
[[ -n "${APP_IMAGE}" ]] && AFTER_CONTAINER="${APP_CONTAINER}"
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

# --compiler <flagtree|triton>: switch the in-container compiler for the runtime
# steps (snapshot + import check). The runtime's `compiler` bash function is
# sourced in every shell (BASH_ENV → /etc/profile.d/zz-compiler.sh); `compiler
# <name>` exports PYTHONPATH to the selected side dir and fails (rc 1) if that
# compiler is absent. Empty = leave the runtime's default compiler active.
COMPILER_GUARD=""
[[ -n "$COMPILER" ]] && COMPILER_GUARD="compiler ${COMPILER} || exit 1"

# ── Print header ────────────────────────────────────────────────────────

echo "========================================"
echo "Megatron Backend Verification"
echo "========================================"
echo "Vendor-Backend:    ${VENDOR_BACKEND}"
echo "Runtime Image:     ${RUNTIME_IMAGE}"
if [[ -n "${APP_IMAGE}" ]]; then
    echo "App Image:         ${APP_IMAGE}"
    echo "Mode:              app-image (install baked at image build time)"
fi
echo "Megatron Version:  ${MEGATRON_VERSION}"
echo "Compiler:          ${COMPILER:-<runtime default>}"
echo ""

# ── Cleanup function ────────────────────────────────────────────────────

cleanup() {
    echo ""
    log_info "Cleaning up containers..."
    docker rm -f "${CONTAINER}" 2>/dev/null || true
    docker rm -f "${APP_CONTAINER}" 2>/dev/null || true
    rm -rf "${WORK_DIR}" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: Start runtime container with hardware access ────────────────

log_step "Step 1: Starting containers"

mkdir -p "${WORK_DIR}"
docker rm -f "${CONTAINER}" 2>/dev/null || true
docker rm -f "${APP_CONTAINER}" 2>/dev/null || true

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

log_info "Container started: ${CONTAINER} (${RUNTIME_IMAGE})"

if [[ -n "${APP_IMAGE}" ]]; then
    docker run -d --name "${APP_CONTAINER}" \
        ${RUN_FLAGS} \
        --network host \
        "${APP_IMAGE}" \
        sleep infinity
    log_info "Container started: ${APP_CONTAINER} (${APP_IMAGE})"
fi

# ── Snapshot helpers ────────────────────────────────────────────────────

# Emits "<pkg> <version> <location>" per watched package; missing package =>
# "<pkg> MISSING". No SDK env sourcing here: the runtime image bakes the
# vendor env via /etc/profile.d + BASH_ENV, so bash -c commands already see
# it (LD_LIBRARY_PATH etc.).
snapshot() {
    local container="${1:-${CONTAINER}}"
    docker exec "${container}" bash -c '
        '"${COMPILER_GUARD}"'
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

if [[ -n "${APP_IMAGE}" ]]; then
    log_step "Step 3: Skipping pip install (app-image mode — megatron-core was installed at image build time)"
else
    log_step "Step 3: Installing megatron-core==${MEGATRON_VERSION}"

    # PYTHONPATH=/opt/triton mirrors the runtime Containerfile DEPS install:
    # pip must see the side-dir triton dist-info, or torch's triton==N dep
    # (declared in the vendor torch METADATA) pulls a fresh triton into
    # site-packages, bypassing the repacked vendor triton (188 MB).
    docker exec "${CONTAINER}" bash -c "
        PYTHONPATH=/opt/triton pip install \
            --index-url '${VENDOR_PYPI}' \
            --extra-index-url '${ALIYUN_PYPI}' \
            'megatron-core==${MEGATRON_VERSION}'
    "

    log_info "megatron-core installed:"
    docker exec "${CONTAINER}" pip show megatron-core | grep -E "^(Name|Version|Location)" || true
fi

# ── Step 4: AFTER snapshot and compare ──────────────────────────────────

log_step "Step 4: AFTER dependency snapshot"

snapshot "${AFTER_CONTAINER}" | tee "${WORK_DIR}/after.txt"

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
    if [[ -n "${APP_IMAGE}" ]]; then
        log_error "Dependency matrix changed — the app-image build was NOT inert. Aborting." >&2
    else
        log_error "Dependency matrix changed — install was NOT inert. Aborting." >&2
    fi
    exit 1
fi
log_info "Dependency matrix intact: torch / triton / flag_gems / numpy unchanged."

# ── Step 5: Import check ────────────────────────────────────────────────

log_step "Step 5: Import check (megatron.core + helpers_cpp)"

docker exec "${AFTER_CONTAINER}" bash -c '
    '"${COMPILER_GUARD}"'
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
if [[ -n "${APP_IMAGE}" ]]; then
    echo "App Image:        ${APP_IMAGE}"
fi
echo ""
echo "To debug:"
echo "  docker exec -it ${CONTAINER} bash"
if [[ -n "${APP_IMAGE}" ]]; then
    echo "  docker exec -it ${APP_CONTAINER} bash"
fi
echo ""
