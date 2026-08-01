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

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

VENDOR_BACKEND="${1:-}"
MODEL_PATH="${MODEL_PATH:-/data/models/Qwen/Qwen3-4B}"
VLLM_VERSION="${VLLM_VERSION:-0.20.2}"
SKIP_SERVE=false
VLLM_VENDOR="cuda"

shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL_PATH="$2"; shift 2 ;;
        --vllm-version) VLLM_VERSION="$2"; shift 2 ;;
        --skip-serve) SKIP_SERVE=true; shift ;;
        --vllm-vendor) VLLM_VENDOR="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 <vendor-backend> [options]"
            echo ""
            echo "Arguments:"
            echo "  vendor-backend     Vendor-backend combo (e.g., mthreads-musa5.2.0)"
            echo ""
            echo "Options:"
            echo "  --model <path>       Path to model for serve test"
            echo "  --vllm-version <ver> vLLM version to install (default: 0.20.2)"
            echo "  --vllm-vendor <vendor> VLLM_VENDOR for plugin build (default: cuda)"
            echo "  --skip-serve          Skip serve test, only install and verify imports"
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

# Read stack version from configs.yaml
if [[ -f "${SCRIPT_DIR}/../configs.yaml" ]]; then
    STACK_VERSION=$(python3 -c "
import yaml
with open('${SCRIPT_DIR}/../configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")
else
    echo "Error: configs.yaml not found"
    exit 1
fi

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
with open('${SCRIPT_DIR}/../.github/build-config.yml') as f:
    config = yaml.safe_load(f)
run_config = config.get('run', {})
vendors = run_config.get('vendors', {})
vendor_config = vendors.get(vendor, {})
# Prefer toolkit over raw
toolkit = vendor_config.get('toolkit', '')
raw = vendor_config.get('raw', '')
print(toolkit if toolkit else raw)
")

docker run -d --name "${CONTAINER}" \
    ${RUN_FLAGS} \
    -v "${WORK_DIR}:${WORK_DIR}" \
    -v "${MODEL_PATH}:${MODEL_PATH}:ro" \
    --network host \
    "${RUNTIME_IMAGE}" \
    sleep infinity

log_info "Container started: ${CONTAINER}"

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
            python3 -c 'import torch; print(f\"MUSA: {torch.musa.is_available() if hasattr(torch, \"musa\") else False}\")'
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

# Check if vendor torch version is older than Aliyun torch
VENDOR_TORCH_OLD=false
case "$VENDOR" in
    mthreads|metax|iluvatar|hygon|kunlunxin|cambricon|sunrise|tsingmicro|enflame)
        VENDOR_TORCH_OLD=true
        ;;
esac

if [[ "$VENDOR_TORCH_OLD" == true ]]; then
    log_info "Using two-step install (vendor torch < Aliyun torch)"
    docker exec "${CONTAINER}" bash -c "
        echo 'Step 3a: Install repacked vllm (no deps)'
        pip install --no-deps --index-url '${VENDOR_PYPI}' 'vllm==${VLLM_VERSION}'

        echo ''
        echo 'Step 3b: Install remaining deps from Aliyun'
        pip install --index-url '${ALIYUN_PYPI}' 'vllm==${VLLM_VERSION}'
    "
else
    log_info "Using single-step install"
    docker exec "${CONTAINER}" bash -c "
        pip install \
            --index-url '${VENDOR_PYPI}' \
            --extra-index-url '${ALIYUN_PYPI}' \
            'vllm==${VLLM_VERSION}'
    "
fi

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

# ── Step 5: Install vllm-plugin-FL ──────────────────────────────────────

log_step "Step 5: Installing vllm-plugin-FL"

docker exec "${CONTAINER}" bash -c "
    cd /workspace
    if [ ! -d vllm-plugin-FL ]; then
        git clone --depth 1 https://github.com/flagos-ai/vllm-plugin-FL.git
    fi
    cd vllm-plugin-FL

    VLLM_VENDOR=${VLLM_VENDOR} pip install --no-build-isolation -e .

    echo ''
    echo 'Plugin installed:'
    pip list | grep -i vllm
"

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
