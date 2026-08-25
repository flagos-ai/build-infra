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
# container and prove the image actually serves training end-to-end: the
# carefully crafted torch/triton/flag_gems/numpy matrix is unchanged after the
# single-step install, megatron.core actually loads, and a mock-data
# pretrain_gpt run (5 iters) exits 0. The wheel keeps its `torch>=2.6.0`
# Requires-Dist; the runtime's vendor torch satisfies it, so pip downloads and
# overwrites nothing.
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
#   ./verify-megatron-backend.sh <vendor-backend> [--megatron-version <ver>] [--app-image <tag>] [--scenario <training|rl>]
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
#   6. E2E training (--scenario training, the default): mock-data pretrain_gpt,
#      5 iters, must exit 0 — proves the image actually serves training.
#      --scenario rl is refused (upstream-blocked: MLF #116 + flash-attn); such
#      cells are marked ⛔ in the status matrix and never collected.

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

MEGATRON_VERSION="${MEGATRON_VERSION:-0.17.1}"
APP_IMAGE="${APP_IMAGE:-}"
COMPILER=""
SCENARIO=""

POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --megatron-version) MEGATRON_VERSION="$2"; shift 2 ;;
        --app-image) APP_IMAGE="$2"; shift 2 ;;
        --compiler) COMPILER="$2"; shift 2 ;;
        --scenario) SCENARIO="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 <vendor-backend> [--megatron-version <ver>] [--app-image <tag>] [--compiler <c>] [--scenario <training|rl>]"
            echo "  --compiler <c>   Compiler path to verify: flagtree | triton (default: runtime default)"
            echo "  --scenario <s>   training (run mock-data pretrain_gpt, the default) | rl (refused — upstream-blocked)"
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

# --scenario defaults to training (the script's primary layer — a cell only
# earns ✅ by running the workload). rl is refused: the GRPO recipe is
# upstream-blocked (MLF #116 + a self-built flash-attn wheel), so rl cells are
# marked ⛔ in the status matrix and never collected by the driver.
SCENARIO="${SCENARIO:-training}"
if [[ "$SCENARIO" != "training" && "$SCENARIO" != "rl" ]]; then
    echo "Error: --scenario must be 'training' or 'rl' (got '$SCENARIO')" >&2
    exit 1
fi
if [[ "$SCENARIO" == "rl" ]]; then
    echo "Error: RL E2E is not automated — upstream-blocked (MLF #116 + flash-attn wheel). Mark this cell ⛔ instead." >&2
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
# stdout is discarded: `compiler triton` prints a status line ("triton (active)
# - 3.6.0"), and the guard is inlined into the snapshot() heredoc where that
# line would otherwise be captured as a second "triton" package record and
# make Step 4b's grep-based comparison report a false "Matrix corrupted".
COMPILER_GUARD=""
[[ -n "$COMPILER" ]] && COMPILER_GUARD="compiler ${COMPILER} >/dev/null || exit 1"

# Per-backend E2E overrides. The training recipe is canonical across backends
# (mock-data pretrain_gpt, 5 iters, seed 42, fixed model size — the validation
# loss is per-platform and NOT cross-backend byte-identical: nvidia 8.360331E+00,
# cambricon 5.973097E+00, ascend 1.084173E+01 in megatron-*-e2e.md), but a few
# backends need local adjustments. Append a branch as each backend earns a
# manual ✅. MASTER_PORT avoids a port collision with a concurrent cell on the
# same node; PREINSTALL fixes a runtime package gap before the single-step
# install — the repacked vendor torch drops torch transitives that
# megatron-core Requires-Dist (psutil) or imports (filelock).
MASTER_PORT="${MASTER_PORT:-29500}"
PREINSTALL=""
PREINSTALL_NOTE=""
case "${VENDOR_BACKEND}" in
    cambricon-neuware4.4.3) MASTER_PORT=29500 ;;
    cambricon-neuware4.7.2) MASTER_PORT=29501 ;;
    nvidia-cuda13.3)
        PREINSTALL="pip install --index-url '${ALIYUN_PYPI}' psutil"
        PREINSTALL_NOTE="psutil (nvidia-cuda13.3 runtime ships none)" ;;
    metax-maca3.7.2.1)
        PREINSTALL="pip install --index-url '${ALIYUN_PYPI}' filelock"
        PREINSTALL_NOTE="filelock (torch transitive stripped from metax repack)" ;;
esac
# NOTE (hygon flagtree): --disable-jit-fuser is INSUFFICIENT there — the jit
# fuser binds torch.compile at import time, before args flip. A container-side
# noop patch (or the upstream lazy-decorator fix) is required before a hygon
# flagtree cell can pass; see megatron-hygon25-e2e.md §1.4. Not scripted here.

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
echo "Scenario:          ${SCENARIO}"
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
    --shm-size=8g \
    "${RUNTIME_IMAGE}" \
    sleep infinity

log_info "Container started: ${CONTAINER} (${RUNTIME_IMAGE})"

if [[ -n "${APP_IMAGE}" ]]; then
    docker run -d --name "${APP_CONTAINER}" \
        ${RUN_FLAGS} \
        --shm-size=8g \
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

    # Per-backend gap fix: preinstall torch transitives dropped by the repacked
    # vendor torch before the single-step install resolves them from aliyun
    # (public PyPI), never the vendor index (megatron-nvidia-e2e.md).
    if [[ -n "${PREINSTALL}" ]]; then
        log_info "Preinstalling ${PREINSTALL_NOTE}"
        docker exec "${CONTAINER}" bash -c "${PREINSTALL}"
    fi

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

# ── Step 6: E2E training (mock-data pretrain_gpt, 5 iters) ──────────────

log_step "Step 6: E2E training (mock-data pretrain_gpt, 5 iters)"

# Canonical recipe (megatron-*-e2e.md §2 baseline, fixed model size, seed 42).
# The merged wheel's dataclass-driven argparse defaults model-size fields to
# None (transformer_config.py `argparse_meta: {"default": None}` on num_layers
# / hidden_size / num_attention_heads / max_position_embeddings / seq_length),
# and validate_args (arguments.py) asserts they are set — so they MUST be
# passed or pretrain_gpt aborts before the first step ("either num-layers or
# encoder-num-layers should be specified"). `--tokenizer-type NullTokenizer
# --vocab-size 50257` forces the synthetic no-download tokenizer: the gpt2
# default (GPT2BPETokenizer) downloads gpt2-vocab.json from S3 via the `wget`
# library, which vendor runtime images lack → `ModuleNotFoundError: wget
# library should be isntalled.` (cambricon app-image runs 32807773771/580).
# `python -m pretrain_gpt` is the
# full-scope wheel's top-level entry (no torchrun); env:// rendezvous needs
# explicit MASTER_ADDR/MASTER_PORT/RANK/WORLD_SIZE.
# TORCHINDUCTOR_COMPILE_THREADS=1 forces inline compile (no fork) — the
# flagtree inductor fork-crash workaround; inert for triton. exit 0 required:
# any crash → script exits non-zero → cell ❌ + debug queue (record path).
docker exec "${AFTER_CONTAINER}" bash -c '
    '"${COMPILER_GUARD}"'
    cd /tmp
    MASTER_ADDR=127.0.0.1 \
    MASTER_PORT='"${MASTER_PORT}"' \
    RANK=0 \
    WORLD_SIZE=1 \
    TORCHINDUCTOR_COMPILE_THREADS=1 \
        python3 -m pretrain_gpt \
            --num-layers 2 --hidden-size 256 --num-attention-heads 4 \
            --max-position-embeddings 1024 --seq-length 1024 \
            --mock-data --train-iters 5 --micro-batch-size 1 --lr 1e-6 --eval-interval 1000 --seed 42 \
            --tokenizer-type NullTokenizer --vocab-size 50257 \
            --transformer-impl local --attention-backend unfused --bf16 \
            --no-masked-softmax-fusion --disable-jit-fuser --no-persist-layer-norm \
            --no-gradient-accumulation-fusion --untie-embeddings-and-output-weights
'
log_info "✅ pretrain_gpt 5-iter E2E exit 0 (scenario=${SCENARIO}, backend=${VENDOR_BACKEND})"

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
