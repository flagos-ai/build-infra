#!/bin/bash
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
# verify-vllm-backend.sh — Install and verify vllm on a specific backend
# ============================================================
#
# Usage:
#   ./verify-vllm-backend.sh <vendor-backend> [options]
#
# Examples:
#   ./verify-vllm-backend.sh mthreads-musa5.2.0
#   ./verify-vllm-backend.sh metax-maca3.7.2.1 --model /data/models/Qwen3-4B
#
# Prerequisites:
#   - Running on target node with hardware access
#   - Docker with runtime image access
#   - repacked vllm wheel already uploaded to vendor PyPI
#
# Steps:
#   1. Start runtime container with hardware access
#   2. Verify torch/triton/flaggems environment
#   3. Install repacked vllm (with +flagos suffix)
#   4. Verify torch version not overwritten
#   5. Install vllm-plugin-FL
#   6. Test vllm serve and inference
#
# --app-image <image>: instead of steps 3-6, verify a prebuilt
#   flagos-dev/vllm-{vendor}-{backend}:{version} image (built by the
#   vllm-app-image workflow): the critical-package matrix
#   (torch/torch_npu/triton/flag_gems/numpy) must be identical to the runtime
#   image's, and vllm + vllm_fl must import. No installs run; serve is skipped.

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

VENDOR_BACKEND="${1:-}"
MODEL_PATH="${MODEL_PATH:-/data/models/Qwen/Qwen3-4B}"
VLLM_VERSION="${VLLM_VERSION:-0.20.2}"
PLUGIN_FL_VERSION="${PLUGIN_FL_VERSION:-}"
SKIP_SERVE=false
VLLM_VENDOR="cuda"
APP_IMAGE=""

shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL_PATH="$2"; shift 2 ;;
        --vllm-version) VLLM_VERSION="$2"; shift 2 ;;
        --plugin-fl-version) PLUGIN_FL_VERSION="$2"; shift 2 ;;
        --skip-serve) SKIP_SERVE=true; shift ;;
        --vllm-vendor) VLLM_VENDOR="$2"; shift 2 ;;
        --app-image) APP_IMAGE="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 <vendor-backend> [options]"
            echo ""
            echo "Arguments:"
            echo "  vendor-backend     Vendor-backend combo (e.g., mthreads-musa5.2.0)"
            echo ""
            echo "Options:"
            echo "  --model <path>       Path to model for serve test"
            echo "  --vllm-version <ver> vLLM version to install (default: 0.20.2)"
            echo "  --plugin-fl-version <ver> vllm-plugin-FL wheel version (default: skip plugin)"
            echo "  --vllm-vendor <vendor> VLLM_VENDOR for plugin build (default: cuda)"
            echo "  --skip-serve          Skip serve test, only install and verify imports"
            echo "  --app-image <image>   Verify a prebuilt vllm app image (matrix + import)"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$VENDOR_BACKEND" ]]; then
    echo "Error: vendor-backend argument required"
    exit 1
fi

# Parse vendor and backend
VENDOR="${VENDOR_BACKEND%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

# ── Configuration ───────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate the repo root: walk up from SCRIPT_DIR until configs.yaml is found.
# Works from any depth inside the tree (e.g. packaging/vllm/) and
# errors cleanly when run on a node without configs.yaml alongside.
REPO_ROOT=""
d="${SCRIPT_DIR}"
while [[ "$d" != "/" ]]; do
    if [[ -f "$d/configs.yaml" ]]; then REPO_ROOT="$d"; break; fi
    d="$(dirname "$d")"
done
if [[ -z "$REPO_ROOT" ]]; then
    echo "Error: configs.yaml not found (searched up from ${SCRIPT_DIR})"
    exit 1
fi

# Read stack version from configs.yaml
STACK_VERSION=$(python3 -c "
import yaml
with open('${REPO_ROOT}/configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")

RUNTIME_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR_BACKEND}:${STACK_VERSION}"
VENDOR_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/simple"
ALIYUN_PYPI="https://mirrors.aliyun.com/pypi/simple"
CONTAINER="vllm-verify-${VENDOR}-${BACKEND}"
WORK_DIR="/tmp/vllm-verify-${VENDOR}-${BACKEND}-$$"

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
echo "vLLM Backend Verification"
echo "========================================"
echo "Vendor-Backend:   ${VENDOR_BACKEND}"
echo "Runtime Image:    ${RUNTIME_IMAGE}"
echo "vLLM Version:     ${VLLM_VERSION}+flagos"
echo "Model Path:       ${MODEL_PATH}"
echo "VLLM_VENDOR:      ${VLLM_VENDOR}"
echo ""

# ── Cleanup function ────────────────────────────────────────────────────

cleanup() {
    echo ""
    log_info "Cleaning up container..."
    docker rm -f "${CONTAINER}" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: Start runtime container with hardware access ────────────────

log_step "Step 1: Starting runtime container"

mkdir -p "${WORK_DIR}"
docker rm -f "${CONTAINER}" 2>/dev/null || true

# Read device flags from build-config.yml
RUN_FLAGS=$(python3 -c "
import yaml
import sys
vendor = '${VENDOR}'
with open('${REPO_ROOT}/.github/build-config.yml') as f:
    config = yaml.safe_load(f)
run_config = config.get('run', {})
vendors = run_config.get('vendors', {})
vendor_config = vendors.get(vendor, {})
# Prefer toolkit over raw
toolkit = vendor_config.get('toolkit', '')
raw = vendor_config.get('raw', '')
print(toolkit if toolkit else raw)
")

# The model mount is only needed for the serve test — skip it in --app-image
# mode (no installs, no serve; the path may not even exist on the node).
MODEL_MOUNT=""
[[ -z "${APP_IMAGE}" ]] && MODEL_MOUNT="-v ${MODEL_PATH}:${MODEL_PATH}:ro"

docker run -d --name "${CONTAINER}" \
    ${RUN_FLAGS} \
    -v "${WORK_DIR}:${WORK_DIR}" \
    ${MODEL_MOUNT} \
    --network host \
    "${RUNTIME_IMAGE}" \
    sleep infinity

log_info "Container started: ${CONTAINER}"

# ── App-image mode: verify a prebuilt vllm app image ─────────────────────
#
# Facility 2 (vllm-app-image.yml) verifies the built
# flagos-dev/vllm-{vendor}-{backend}:{version} image instead of installing
# from scratch: BEFORE snapshot from the runtime image, AFTER from the app
# image — the critical-package matrix (torch / torch_npu / triton /
# flag_gems / numpy) must match item by item, proving the single-step wheel
# installs baked into the image were inert. Then import vllm + vllm_fl on
# the app container. No install steps run; the serve test is skipped.
if [[ -n "${APP_IMAGE}" ]]; then
    log_step "App-image mode: verifying ${APP_IMAGE}"

    APP_CONTAINER="vllm-app-verify-${VENDOR}-${BACKEND}"
    docker rm -f "${APP_CONTAINER}" 2>/dev/null || true

    WATCH_PKGS="torch torch_npu triton flag_gems numpy"
    snapshot() {
        local cid="$1" pkg ver
        for pkg in ${WATCH_PKGS}; do
            ver=$(docker exec "${cid}" python3 -c \
                "import importlib.metadata as m; print(m.version('${pkg}'))" \
                2>/dev/null || echo "NOT_INSTALLED")
            echo "${pkg}=${ver}"
        done
    }

    log_step "BEFORE snapshot (runtime image)"
    snapshot "${CONTAINER}" | tee "${WORK_DIR}/before.txt"

    docker run -d --name "${APP_CONTAINER}" \
        ${RUN_FLAGS} \
        --network host \
        "${APP_IMAGE}" \
        sleep infinity
    log_info "App container started: ${APP_CONTAINER}"

    log_step "AFTER snapshot (app image)"
    snapshot "${APP_CONTAINER}" | tee "${WORK_DIR}/after.txt"

    log_step "Comparing critical-package matrix"
    if diff -u "${WORK_DIR}/before.txt" "${WORK_DIR}/after.txt"; then
        log_info "✅ Matrix unchanged: the app image did not overwrite runtime packages"
    else
        log_error "❌ Matrix changed: the app image overwrote a runtime package"
        docker rm -f "${APP_CONTAINER}" 2>/dev/null || true
        exit 1
    fi

    log_step "Import check (vllm + vllm_fl)"
    if docker exec "${APP_CONTAINER}" bash -c \
        'python3 -c "import vllm, vllm_fl; print(\"vllm\", vllm.__version__, \"| plugin ok\")"'; then
        log_info "✅ vllm + vllm_fl import OK"
    else
        log_error "❌ import failed"
        docker rm -f "${APP_CONTAINER}" 2>/dev/null || true
        exit 1
    fi

    docker rm -f "${APP_CONTAINER}" 2>/dev/null || true
    log_info "App-image verification PASSED"
    exit 0
fi

# ── Step 2: Verify runtime environment ──────────────────────────────────

log_step "Step 2: Verifying runtime environment"

docker exec "${CONTAINER}" bash -c "
    echo '--- Python ---'
    python3 --version

    echo ''
    echo '--- Torch ---'
    python3 -c 'import torch; print(f\"torch: {torch.__version__}\")'

    echo ''
    echo '--- NumPy ---'
    python3 -c 'import numpy; print(f\"numpy: {numpy.__version__}\")'

    echo ''
    echo '--- Triton ---'
    python3 -c 'import triton; print(f\"triton: {triton.__version__}\")'

    echo ''
    echo '--- FlagGems ---'
    python3 -c 'import flag_gems; print(f\"flag_gems: {flag_gems.__version__}\")'

    echo ''
    echo '--- Device availability ---'
    case '${VENDOR}' in
        nvidia)
            nvidia-smi 2>/dev/null || echo 'nvidia-smi not available'
            ;;
        mthreads)
            mthreads-gmi 2>/dev/null || echo 'mthreads-gmi not available'
            ;;
        metax)
            mx-smi 2>/dev/null || echo 'mx-smi not available'
            ;;
        hygon)
            hy-smi 2>/dev/null || echo 'hy-smi not available'
            ;;
        iluvatar)
            ixsmi 2>/dev/null || echo 'ixsmi not available'
            ;;
    esac
"

# ── Step 3: Install repacked vllm ───────────────────────────────────────

log_step "Step 3: Installing repacked vllm"

# Install vllm+flagos from the vendor PyPI (primary), with Aliyun as
# fallback.  All repacked wheels (vllm + xgrammar + compressed-tensors +
# opencv-python-headless, all carrying the +flagos suffix) live on the
# vendor index alongside that backend's torch/flag_gems; everything else
# resolves from Aliyun.  opencv's numpy declaration is stripped in the
# repacked wheel, so a single-step install with a pinned numpy no longer
# hits ResolutionImpossible.
docker exec "${CONTAINER}" bash -c "
    pip install \
        --index-url '${VENDOR_PYPI}' \
        --extra-index-url '${ALIYUN_PYPI}' \
        'vllm==${VLLM_VERSION}'
"

log_info "vllm installed:"
docker exec "${CONTAINER}" pip show vllm | grep -E "^(Name|Version|Location)"

# ── Step 4: Verify torch not overwritten ────────────────────────────────

log_step "Step 4: Verifying torch version"

docker exec "${CONTAINER}" bash -c "
    TORCH_VER=\$(python3 -c 'import torch; print(torch.__version__)')
    echo \"Torch version: \${TORCH_VER}\"

    case '${VENDOR}' in
        mthreads)
            if [[ \"\${TORCH_VER}\" == *musa* ]]; then
                echo '✅ Torch is vendor version (+musa)'
            else
                echo '❌ ERROR: Torch overwritten! Expected +musa suffix'
                exit 1
            fi
            ;;
        metax)
            if [[ \"\${TORCH_VER}\" == *metax* ]]; then
                echo '✅ Torch is vendor version (+metax)'
            else
                echo '❌ ERROR: Torch overwritten! Expected +metax suffix'
                exit 1
            fi
            ;;
        nvidia)
            if [[ \"\${TORCH_VER}\" == *cu* ]]; then
                echo '✅ Torch is CUDA version'
            else
                echo '❌ ERROR: Torch overwritten! Expected +cuXXX suffix'
                exit 1
            fi
            ;;
        *)
            echo '⚠️  Manual verification needed for vendor: ${VENDOR}'
            ;;
    esac
"

# ── Step 5: Install vllm-plugin-FL (wheel) ──────────────────────────────

log_step "Step 5: Installing vllm-plugin-FL"

if [[ -z "${PLUGIN_FL_VERSION}" ]]; then
    log_warn "No --plugin-fl-version given; skipping plugin install"
    log_warn "Pass --plugin-fl-version <version> to install the audited plugin wheel"
else
    # Clean single-step install from the vendor PyPI, same index pair as
    # vllm. The wheel's Requires-Dist is audited to be empty of the runtime's
    # critical packages (packaging/vllm/audit-deps.py), so pip has no reason
    # to touch the baked torch/triton/flag_gems matrix.
    docker exec "${CONTAINER}" bash -c "
        pip install \
            --index-url '${VENDOR_PYPI}' \
            --extra-index-url '${ALIYUN_PYPI}' \
            'vllm-plugin-fl==${PLUGIN_FL_VERSION}'

        echo ''
        echo 'Plugin installed:'
        pip show vllm-plugin-fl | grep -E '^(Name|Version|Location)'
    "
fi

# ── Step 6: Test vllm serve ─────────────────────────────────────────────

if [[ "$SKIP_SERVE" == true ]]; then
    log_info "Step 6: Skipping serve test (--skip-serve)"
else
    log_step "Step 6: Testing vllm serve"

    if [[ ! -d "$MODEL_PATH" ]]; then
        log_warn "Model not found at: $MODEL_PATH"
        log_info "Set MODEL_PATH environment variable to test inference"
        log_info "Skipping serve test"
    else
        log_info "Starting vllm serve (this may take several minutes)..."

        docker exec "${CONTAINER}" bash -c "
            export VLLM_PLUGINS=fl
            export VLLM_FL_DISPATCH_DEBUG=1

            python3 -c 'import vllm; print(\"✅ vllm imported successfully\")'

            echo ''
            echo 'Starting serve...'
            vllm serve '${MODEL_PATH}' \
                --port 8031 \
                --gpu-memory-utilization 0.6 \
                --enforce-eager \
                --trust-remote-code \
                --max-model-len 2048 \
                2>&1 &

            SERVE_PID=\$!
            echo 'Waiting for serve to start (60s)...'
            sleep 60

            echo ''
            echo 'Sending test request...'
            RESPONSE=\$(curl -s http://127.0.0.1:8031/v1/completions \
                -H 'Content-Type: application/json' \
                -d '{\"model\":\"'\${MODEL_PATH}'\",\"prompt\":\"The capital of France is\",\"max_tokens\":16,\"temperature\":0}' 2>/dev/null)

            if echo \"\${RESPONSE}\" | grep -q 'Paris\|capital\|France'; then
                echo '✅ Inference test passed'
                echo \"Response: \${RESPONSE}\"
            else
                echo '❌ Inference test failed'
                echo \"Response: \${RESPONSE}\"
            fi

            kill \${SERVE_PID} 2>/dev/null || true
        "
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────

echo ""
echo "========================================"
echo "Verification Summary"
echo "========================================"
echo "Backend:          ${VENDOR_BACKEND}"
echo "vLLM Version:     ${VLLM_VERSION}+flagos"
echo "Container:        ${CONTAINER}"
echo ""
echo "Status:"
docker exec "${CONTAINER}" bash -c "
    echo -n 'vllm: '; python3 -c 'import vllm; print(vllm.__version__)' 2>/dev/null || echo 'FAILED'
    echo -n 'torch: '; python3 -c 'import torch; print(torch.__version__)' 2>/dev/null || echo 'FAILED'
    echo -n 'flag_gems: '; python3 -c 'import flag_gems; print(flag_gems.__version__)' 2>/dev/null || echo 'FAILED'
"
echo ""
echo "To debug:"
echo "  docker exec -it ${CONTAINER} bash"
echo ""
