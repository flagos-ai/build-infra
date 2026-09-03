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
# --app-image <image>: instead of steps 3-5, verify a prebuilt
#   flagos-app/vllm{vllm_version}-{vendor}-{backend}:{version}[-{plugin}] image
#   (built by the
#   vllm-app-image workflow): the critical-package matrix
#   (torch/torch_npu/triton/flag_gems/numpy) must be identical to the runtime
#   image's, and vllm + vllm_fl must import. No installs run; the serve test
#   (Step 6) still runs against the app image — a cell only earns ✅ by
#   returning a real completion.

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

VENDOR_BACKEND="${1:-}"
MODEL_PATH="${MODEL_PATH:-/data/models/Qwen/Qwen3-4B}"
VLLM_VERSION="${VLLM_VERSION:-0.20.2}"
PLUGIN_FL_VERSION="${PLUGIN_FL_VERSION:-}"
SKIP_SERVE=false
# Serve-test time budget in seconds, shared by the readiness poll window and
# the completion request. 1800s default because first-compile cold starts
# vary wildly by backend: cambricon ~250s, tsingmicro engine init alone was
# 899s + startup ≈ 18.5 min (docs/vllm-0.24.0/backends/tsingmicro.md §15).
SERVE_TIMEOUT=1800
APP_IMAGE=""
COMPILER=""
# Stack version driving the runtime image tag. Empty = read from the repo's
# own configs.yaml (REPO_ROOT below); explicit --stack-version = use exactly
# this version, for when the checkout is stale and you don't want to refresh.
STACK_VERSION=""

shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL_PATH="$2"; shift 2 ;;
        --vllm-version) VLLM_VERSION="$2"; shift 2 ;;
        --plugin-fl-version) PLUGIN_FL_VERSION="$2"; shift 2 ;;
        --skip-serve) SKIP_SERVE=true; shift ;;
        --serve-timeout) SERVE_TIMEOUT="$2"; shift 2 ;;
        --app-image) APP_IMAGE="$2"; shift 2 ;;
        --compiler) COMPILER="$2"; shift 2 ;;
        --stack-version) STACK_VERSION="$2"; shift 2 ;;
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
            echo "  --skip-serve          Skip serve test, only install and verify imports"
            echo "  --serve-timeout <sec> Time budget for serve readiness + completion (default: 1800)"
            echo "  --app-image <image>   Verify a prebuilt vllm app image (matrix + import)"
            echo "  --compiler <c>        Compiler path to verify: flagtree | triton (default: runtime default)"
            echo "  --stack-version <ver> Stack version for the runtime image tag; default: read from the discovered configs.yaml"
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

if [[ -n "$COMPILER" && "$COMPILER" != "flagtree" && "$COMPILER" != "triton" ]]; then
    echo "Error: --compiler must be 'flagtree' or 'triton' (got '$COMPILER')" >&2
    exit 1
fi

if ! [[ "$SERVE_TIMEOUT" =~ ^[0-9]+$ ]] || [[ "$SERVE_TIMEOUT" -lt 60 ]]; then
    echo "Error: --serve-timeout must be an integer ≥ 60 (got '$SERVE_TIMEOUT')" >&2
    exit 1
fi

# ── Configuration ───────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate the repo root: this script lives at packaging/vllm/verify/ in the
# checkout, so the root is a FIXED relative path — never a walk-up search. A
# copy staged elsewhere (the old "sed SCRIPT_DIR" → /tmp pattern) resolves to
# a directory with no configs.yaml and fails loudly here, instead of silently
# picking up whatever configs.yaml happens to be nearby. (Three levels up:
# packaging/vllm/verify/ — the megatron verify script at the same depth uses
# the same ../../.. .)
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
if [[ ! -f "${REPO_ROOT}/configs.yaml" ]]; then
    echo "Error: configs.yaml not found at ${REPO_ROOT} (expected the repo root). Run this script from the repo checkout — do not stage it to /tmp." >&2
    exit 1
fi

# Read stack version from configs.yaml. Explicit --stack-version wins;
# otherwise it is read from ${REPO_ROOT}/configs.yaml — only correct if the
# checkout is fresh (refresh the node first). The source is echoed in the
# header so every log line shows which one drove the image tag.
if [[ -z "${STACK_VERSION}" ]]; then
    STACK_VERSION=$(python3 -c "
import yaml
with open('${REPO_ROOT}/configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")
    STACK_VERSION_SOURCE="${REPO_ROOT}/configs.yaml (discovered)"
else
    STACK_VERSION_SOURCE="--stack-version (explicit)"
fi

RUNTIME_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR_BACKEND}:${STACK_VERSION}"
VENDOR_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/simple"
ALIYUN_PYPI="https://mirrors.aliyun.com/pypi/simple"
CONTAINER="vllm-verify-${VENDOR}-${BACKEND}"
APP_CONTAINER="vllm-app-verify-${VENDOR}-${BACKEND}"
# Which container the serve test (Step 6) runs against: the app image container
# in --app-image mode, the installed runtime container otherwise.
SERVE_CONTAINER="${CONTAINER}"
[[ -n "${APP_IMAGE}" ]] && SERVE_CONTAINER="${APP_CONTAINER}"
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

# --compiler <flagtree|triton>: switch the in-container compiler for the runtime
# steps (env check + serve). The runtime's `compiler` bash function is sourced in
# every shell (BASH_ENV → /etc/profile.d/zz-compiler.sh); `compiler <name>` exports
# PYTHONPATH to the selected side dir and fails (rc 1) if that compiler is absent.
# Empty = leave the runtime's default compiler active.
COMPILER_GUARD=""
[[ -n "$COMPILER" ]] && COMPILER_GUARD="compiler ${COMPILER} || exit 1"

# ── Print header ────────────────────────────────────────────────────────

echo "========================================"
echo "vLLM Backend Verification"
echo "========================================"
echo "Vendor-Backend:   ${VENDOR_BACKEND}"
echo "Runtime Image:    ${RUNTIME_IMAGE}"
echo "Stack Version:    ${STACK_VERSION} (${STACK_VERSION_SOURCE})"
echo "vLLM Version:     ${VLLM_VERSION}+flagos"
echo "Compiler:         ${COMPILER:-<runtime default>}"
echo "Model Path:       ${MODEL_PATH}"
echo ""

# ── Cleanup function ────────────────────────────────────────────────────

cleanup() {
    echo ""
    log_info "Cleaning up containers..."
    docker rm -f "${CONTAINER}" 2>/dev/null || true
    docker rm -f "${APP_CONTAINER}" 2>/dev/null || true
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

# Some vendor toolkits (e.g. enflame) already carry `--network host` in their
# run flags; adding it again makes docker abort with "network host is
# specified multiple times", so only inject it when the flags do not name one.
if [[ " ${RUN_FLAGS} " != *" --network "* ]]; then
    RUN_FLAGS="${RUN_FLAGS} --network host"
fi

# The model mount is only needed for the serve test. Mount it read-only when
# the node has the model dir; the serve test (Step 6) exits 1 when it is absent
# rather than silently skipping.
MODEL_MOUNT=""
[[ -d "${MODEL_PATH}" ]] && MODEL_MOUNT="-v ${MODEL_PATH}:${MODEL_PATH}:ro"

docker run -d --name "${CONTAINER}" \
    ${RUN_FLAGS} \
    -v "${WORK_DIR}:${WORK_DIR}" \
    ${MODEL_MOUNT} \
    "${RUNTIME_IMAGE}" \
    sleep infinity

log_info "Container started: ${CONTAINER}"

# ── App-image mode: verify a prebuilt vllm app image ─────────────────────
#
# Facility 2 (vllm-app-image.yml) verifies the built
# flagos-app/vllm{vllm_version}-{vendor}-{backend}:{version}[-{plugin}] image
# instead of installing
# from scratch: BEFORE snapshot from the runtime image, AFTER from the app
# image — the critical-package matrix (torch / torch_npu / triton /
# flag_gems / numpy) must match item by item, proving the single-step wheel
# installs baked into the image were inert. Then import vllm + vllm_fl on
# the app container. No install steps run; the serve test still runs against
# the app container.
if [[ -n "${APP_IMAGE}" ]]; then
    log_step "App-image mode: verifying ${APP_IMAGE}"

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
        ${MODEL_MOUNT} \
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

    log_info "App-image import check PASSED — proceeding to serve test (Step 6)"
fi

# ── Step 2: Verify runtime environment ──────────────────────────────────

log_step "Step 2: Verifying runtime environment"

docker exec "${CONTAINER}" bash -c "
    ${COMPILER_GUARD}
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
        tsingmicro)
            tsm_smi 2>/dev/null || echo 'tsm_smi not available'
            ;;
    esac
"

# ── Steps 3-5: install vllm + plugin into the RUNTIME container ─────────
#
# From-scratch path only. In --app-image mode these installs are already baked
# into the image and were verified by the matrix diff above, so they are
# skipped; Step 6 (serve) still runs against the app image.
if [[ -z "${APP_IMAGE}" ]]; then

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
        'vllm==${VLLM_VERSION}+flagos'
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
        tsingmicro)
            if [[ \"\${TORCH_VER}\" == *+cpu* ]]; then
                echo '✅ Torch is vendor version (+cpu)'
            else
                echo '❌ ERROR: Torch overwritten! Expected +cpu suffix'
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
    # critical packages (packaging/script/audit-deps.py), so pip has no reason
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

fi

# ── Step 6: Test vllm serve (real completion required) ───────────────────

if [[ "$SKIP_SERVE" == true ]]; then
    log_info "Step 6: Skipping serve test (--skip-serve — manual debugging only)"
else
    log_step "Step 6: Testing vllm serve (real completion required)"

    if [[ ! -d "$MODEL_PATH" ]]; then
        log_error "Model not found at: $MODEL_PATH"
        log_error "A serve test needs a real model — refusing to skip. Set MODEL_PATH"
        log_error "(or pass --skip-serve for manual debugging only)."
        exit 1
    fi

    log_info "Starting vllm serve on ${SERVE_CONTAINER} (this may take several minutes)..."

    # A decode that actually answers "The capital of France is" names Paris.
    # Broken decodes (mojibake / sampling corruption — e.g. enflame served
    # under the wrong compiler, 2026-09-03) still return HTTP 200 + non-empty
    # text, so a status check alone lets garbage pass as a ✅. Assert the
    # anchor for the matrix model; custom-model runs (mthreads-4.3.6 serves a
    # DeepSeek model, no Qwen3-4B) opt out so they do not false-fail.
    EXPECT_ANCHOR=""
    case "$MODEL_PATH" in
        *Qwen3-4B*) EXPECT_ANCHOR="Paris" ;;
    esac

    docker exec "${SERVE_CONTAINER}" bash -c "
        ${COMPILER_GUARD}
        export VLLM_PLUGINS=fl
        export VLLM_FL_DISPATCH_DEBUG=1
        export SERVE_TIMEOUT=${SERVE_TIMEOUT}

        echo ''
        echo 'Starting serve...'
        vllm serve '${MODEL_PATH}' \
            --port 8031 \
            --gpu-memory-utilization 0.6 \
            --enforce-eager \
            --trust-remote-code \
            --max-model-len 2048 \
            > /tmp/vllm-serve.log 2>&1 &

        SERVE_PID=\$!
        # Poll the log for readiness (up to SERVE_TIMEOUT). First-compile
        # warmup varies wildly by backend — cambricon MLU590 Qwen3-4B warmup
        # + kv-cache profile took 249.9s on a clean node, tsingmicro engine
        # init alone was 899s + startup ≈ 18.5 min cold (docs/
        # vllm-0.24.0/backends/tsingmicro.md §15) — so the window is
        # configurable via --serve-timeout (default 1800s).
        echo 'Waiting for serve to become ready...'
        ready=0
        for i in \$(seq 1 \$((SERVE_TIMEOUT / 5))); do
            if ! kill -0 \${SERVE_PID} 2>/dev/null; then
                echo 'serve process exited during startup'
                break
            fi
            if grep -qE 'Application startup complete|Uvicorn running' /tmp/vllm-serve.log 2>/dev/null; then
                ready=1
                echo \"serve ready after ~\$((i*5))s\"
                break
            fi
            sleep 5
        done
        if [ \"\$ready\" != \"1\" ]; then
            echo 'serve did not become ready in time; last 40 lines of log:'
            tail -40 /tmp/vllm-serve.log 2>/dev/null || true
            kill \${SERVE_PID} 2>/dev/null || true
            exit 1
        fi

        echo ''
        echo 'Sending test request...'
        python3 - <<'PY'
import json, urllib.request, sys
req = urllib.request.Request(
    'http://127.0.0.1:8031/v1/completions',
    data=json.dumps({'prompt': 'The capital of France is', 'max_tokens': 16, 'temperature': 0}).encode(),
    headers={'Content-Type': 'application/json'},
)
try:
    # First request on a cold serve compiles triton kernels per-shape — on
    # cambricon MLU590 that runs ~60s+ (docs/vllm-0.20.2/backends/cambricon.md
    # §2.7: 60s curl timed out, 300s returned). SERVE_TIMEOUT leaves headroom
    # on a shared node and on slow-cold-start backends (tsingmicro §15).
    with urllib.request.urlopen(req, timeout=$SERVE_TIMEOUT) as resp:
        status, body = resp.status, json.loads(resp.read())
except Exception as e:
    print('request failed:', e)
    sys.exit(1)
text = (body.get('choices') or [{}])[0].get('text') or ''
if status != 200 or not text:
    print('no completion: status=%s body=%r' % (status, body))
    sys.exit(1)
expect = \"${EXPECT_ANCHOR}\"
if expect and expect not in text:
    print('completion failed semantic check: expected %r in text %r' % (expect, text))
    sys.exit(1)
print('completion returned (status=%s): %r' % (status, text))
PY

        rc=\$?
        kill \${SERVE_PID} 2>/dev/null || true
        exit \$rc
    "
fi

# ── Summary ─────────────────────────────────────────────────────────────

echo ""
echo "========================================"
echo "Verification Summary"
echo "========================================"
echo "Backend:          ${VENDOR_BACKEND}"
echo "vLLM Version:     ${VLLM_VERSION}+flagos"
echo "Container:        ${SERVE_CONTAINER}"
echo ""
echo "Status:"
docker exec "${SERVE_CONTAINER}" bash -c "
    echo -n 'vllm: '; python3 -c 'import vllm; print(vllm.__version__)' 2>/dev/null || echo 'FAILED'
    echo -n 'torch: '; python3 -c 'import torch; print(torch.__version__)' 2>/dev/null || echo 'FAILED'
    echo -n 'flag_gems: '; python3 -c 'import flag_gems; print(flag_gems.__version__)' 2>/dev/null || echo 'FAILED'
"
echo ""
echo "To debug:"
echo "  docker exec -it ${CONTAINER} bash"
echo ""
