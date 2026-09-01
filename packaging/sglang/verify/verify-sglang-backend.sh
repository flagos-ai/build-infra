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
# verify-sglang-backend.sh — Install and verify sglang 0.5.18 on a backend
# ============================================================
#
# Install `sglang==<ver>+flagos` plus the sglang_fl plugin wheel into a
# `flagos-runtime-{vendor}-{backend}` container and prove the image actually
# serves inference end-to-end: the torch/triton/flag_gems/numpy matrix is
# unchanged after the installs, sglang + sgl_kernel + sglang_fl import, and a
# Qwen3-0.6B serve answers 3× chat/completions with HTTP 200 +
# completion_tokens=144 + sampling_backend=pytorch (playbook §5.5). The
# runtime switches are exported BEFORE the install; the flag_gems SQL
# ConfigCache is cleared before serve so the F and T compiler paths never
# cross-pollinate (playbook §5.4).
#
# The plugin is NOT on any index: it is built in-container from the
# sglang-plugin-FL repo (exp/0.5.18 branch) — git clone + `pip wheel` — then
# pip-installed. Same recipe the app image build will replay.
#
# One compiler per invocation (--compiler F or T); a cell only earns ✅ when
# both invocations pass (F = flagtree, the runtime default, T = vendor triton).
#
# Usage:
#   ./verify-sglang-backend.sh <vendor-backend> [--compiler <flagtree|triton|F|T>] [--device <n>] [--model <dir>] [--sglang-version <ver>] [--plugin-ref <ref>] [--serve-timeout <sec>] [--skip-serve] [--stack-version <ver>]
#
# Examples:
#   ./verify-sglang-backend.sh metax-maca3.7.2.1 --compiler F
#   ./verify-sglang-backend.sh metax-maca3.7.2.1 --compiler T --device 1 --model /data/models/Qwen/Qwen3-0.6B
#
# Prerequisites:
#   - Running on the target node with hardware access
#   - `sglang==<ver>+flagos` wheel uploaded to the vendor PyPI
#     (flagos-pypi-<vendor>)
#   - Qwen3-0.6B model dir on the node (default /data/models/Qwen/Qwen3-0.6B)
#   - Container reachability to github.com (plugin clone)
#
# Steps:
#   1. Start runtime container with hardware access (build-config.yml run flags)
#   2. BEFORE snapshot: torch / triton / flag_gems / numpy (+ site-package path)
#   3. Single-step install of sglang==<ver>+flagos (runtime switches exported)
#   4. Build + install the sglang_fl plugin (in-container, not on the node)
#   5. AFTER snapshot: every watched package must equal BEFORE — the installs
#      were inert
#   6. Import check: sglang + sgl_kernel + sglang_fl
#   7. E2E serve: 3× chat/completions (HTTP 200 + completion_tokens=144 +
#      sampling_backend=pytorch)

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

MODEL_PATH="${MODEL_PATH:-/data/models/Qwen/Qwen3-0.6B}"
SGLANG_VERSION="${SGLANG_VERSION:-0.5.18}"
PLUGIN_REF="${PLUGIN_REF:-exp/0.5.18}"
PLUGIN_REPO="https://github.com/flagos-ai/sglang-plugin-FL"
SKIP_SERVE=false
# Serve-test time budget in seconds, shared by the readiness poll window and
# each completion request. 1800s default because cold-start first-compile
# varies wildly by backend (same reasoning as the vllm verify script).
SERVE_TIMEOUT="${SERVE_TIMEOUT:-1800}"
# HTTP port for the serve test. 8032 — distinct from the vllm script's 8031
# so a concurrent vllm cell on the same node does not collide.
SGLANG_PORT="${SGLANG_PORT:-8032}"
COMPILER=""
DEVICE=""
# Stack version driving the runtime image tag. Empty = read from the repo's
# own configs.yaml (REPO_ROOT below); explicit --stack-version = use exactly
# this version, for when the checkout is stale and you don't want to refresh.
STACK_VERSION=""

POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL_PATH="$2"; shift 2 ;;
        --sglang-version) SGLANG_VERSION="$2"; shift 2 ;;
        --plugin-ref) PLUGIN_REF="$2"; shift 2 ;;
        --skip-serve) SKIP_SERVE=true; shift ;;
        --serve-timeout) SERVE_TIMEOUT="$2"; shift 2 ;;
        --compiler) COMPILER="$2"; shift 2 ;;
        --device) DEVICE="$2"; shift 2 ;;
        --stack-version) STACK_VERSION="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 <vendor-backend> [options]"
            echo ""
            echo "Arguments:"
            echo "  vendor-backend     Vendor-backend combo (e.g., metax-maca3.7.2.1)"
            echo ""
            echo "Options:"
            echo "  --compiler <c>       Compiler path to verify: flagtree|F | triton|T (default: runtime default)"
            echo "  --device <n>         Pin to one visible device (env-pinnable vendors; refused elsewhere)"
            echo "  --model <dir>        Path to model for serve test (default: /data/models/Qwen/Qwen3-0.6B)"
            echo "  --sglang-version <ver>  sglang version to install (default: 0.5.18; +flagos suffix appended)"
            echo "  --plugin-ref <ref>   sglang-plugin-FL branch/tag/sha to build the plugin from (default: exp/0.5.18)"
            echo "  --skip-serve         Skip serve test, only install and verify imports"
            echo "  --serve-timeout <sec> Time budget for serve readiness + each completion (default: 1800)"
            echo "  --stack-version <ver> Stack version for the runtime image tag; default: read from the discovered configs.yaml"
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

# --compiler accepts both long and one-letter forms (F/T from the status
# matrix) — normalize to the `compiler` function's spelling.
case "${COMPILER,,}" in
    "") COMPILER="" ;;
    f|flagtree) COMPILER="flagtree" ;;
    t|triton)   COMPILER="triton" ;;
    *)
        echo "Error: --compiler must be 'flagtree' (F) or 'triton' (T) (got '$COMPILER')" >&2
        exit 1
        ;;
esac

if [[ -n "$DEVICE" && ! "$DEVICE" =~ ^[0-9,]+$ ]]; then
    echo "Error: --device must be a device index or comma list (got '$DEVICE')" >&2
    exit 1
fi

if ! [[ "$SERVE_TIMEOUT" =~ ^[0-9]+$ ]] || [[ "$SERVE_TIMEOUT" -lt 60 ]]; then
    echo "Error: --serve-timeout must be an integer ≥ 60 (got '$SERVE_TIMEOUT')" >&2
    exit 1
fi

# ── Configuration ───────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate the repo root: this script lives at packaging/sglang/verify/ in the
# checkout, so the root is a FIXED relative path — never a walk-up search. A
# copy staged elsewhere (the old "sed SCRIPT_DIR" → /tmp pattern) resolves to
# a directory with no configs.yaml and fails loudly here, instead of silently
# picking up whatever configs.yaml happens to be nearby.
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
if [[ ! -f "${REPO_ROOT}/configs.yaml" ]]; then
    echo "Error: configs.yaml not found at ${REPO_ROOT} (expected the repo root). Run this script from the repo checkout — do not stage it to /tmp." >&2
    exit 1
fi

# Stack version for the runtime image tag. Explicit --stack-version wins;
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
CONTAINER="sglang-verify-${VENDOR}-${BACKEND}"
WORK_DIR="/tmp/sglang-verify-${VENDOR}-${BACKEND}-$$"

# Packages that must survive the installs bit-for-bit (single-step install
# inertness — the app Containerfile build-step replay).
WATCH_PKGS="torch triton flag_gems numpy"

# Runtime switches from playbook §5.2/§5.5: skip flashinfer (not present on
# vendor runtimes), inline inductor compile (the flagtree fork-crash
# workaround; inert for triton), and skip the sgl_kernel shim version hard
# check. Exported in every shell that installs or runs sglang — the runtime
# image does NOT bake them, and each docker exec is a fresh shell.
SGLANG_SWITCHES="export SGLANG_IS_FLASHINFER_AVAILABLE=false TORCHINDUCTOR_COMPILE_THREADS=1 SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1"

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

# --compiler <flagtree|triton>: switch the in-container compiler for every
# runtime step (snapshot + import + serve). The runtime's `compiler` bash
# function is sourced in every shell (BASH_ENV → /etc/profile.d/zz-compiler.sh);
# `compiler <name>` exports PYTHONPATH to the selected side dir (/opt/flagtree
# or /opt/triton) and fails (rc 1) if that compiler is absent. Empty = leave
# the runtime's default compiler active. stdout is discarded: `compiler triton`
# prints a status line, and in the snapshot() heredoc that line would be
# captured as a second "triton" record and make the Step 5b comparison report
# a false "Matrix corrupted" (same guard as the megatron verify script).
COMPILER_GUARD=""
[[ -n "$COMPILER" ]] && COMPILER_GUARD="compiler ${COMPILER} >/dev/null || exit 1"

# --device <n>: pin the run to one visible device (the iluvatar run_ix_verify
# replica pattern). The env var is the vendor's own, as used in
# build-config.yml run.vendors.<vendor>.toolkit — appended AFTER the RUN_FLAGS
# so docker's last-wins env override applies. Vendors whose device visibility
# is defined by raw device mounts (metax/cambricon/sunrise) cannot be pinned
# by env; --device is refused there rather than silently ignored.
DEVICE_ENV=""
if [[ -n "$DEVICE" ]]; then
    case "${VENDOR}" in
        nvidia)     DEVICE_ENV="-e CUDA_VISIBLE_DEVICES=${DEVICE}" ;;
        ascend)     DEVICE_ENV="-e ASCEND_VISIBLE_DEVICES=${DEVICE}" ;;
        hygon)      DEVICE_ENV="-e DCU_VISIBLE_DEVICES=${DEVICE}" ;;
        mthreads)   DEVICE_ENV="-e MTHREADS_VISIBLE_DEVICES=${DEVICE}" ;;
        iluvatar)   DEVICE_ENV="-e IX_VISIBLE_DEVICES=${DEVICE}" ;;
        kunlunxin)  DEVICE_ENV="-e CXPU_VISIBLE_DEVICES=${DEVICE}" ;;
        tsingmicro) DEVICE_ENV="-e TSINGMICRO_VISIBLE_DEVICES=${DEVICE}" ;;
        enflame)    DEVICE_ENV="-e ENFLAME_VISIBLE_DEVICES=${DEVICE}" ;;
        *)
            echo "Error: --device is not supported for ${VENDOR} — device visibility is defined by raw device mounts, not an env var" >&2
            exit 1
            ;;
    esac
fi

# ── Print header ────────────────────────────────────────────────────────

echo "========================================"
echo "sglang Backend Verification"
echo "========================================"
echo "Vendor-Backend:   ${VENDOR_BACKEND}"
echo "Runtime Image:    ${RUNTIME_IMAGE}"
echo "Stack Version:    ${STACK_VERSION} (${STACK_VERSION_SOURCE})"
echo "sglang Version:   ${SGLANG_VERSION}+flagos"
echo "Plugin Ref:       ${PLUGIN_REF} (${PLUGIN_REPO})"
echo "Compiler:         ${COMPILER:-<runtime default>}"
echo "Model Path:       ${MODEL_PATH}"
if [[ -n "$DEVICE" ]]; then
    echo "Device Pin:       ${DEVICE} (${DEVICE_ENV#-e })"
fi
echo ""

# ── Cleanup function ────────────────────────────────────────────────────

cleanup() {
    echo ""
    log_info "Container kept for audit (persistent-container discipline)"
    local cid
    cid=$(docker ps --filter "name=${CONTAINER}" --format '{{.ID}}' 2>/dev/null | head -1)
    echo "  Container id:   ${cid:-<not running>}  (name: ${CONTAINER})"
    echo "  Serve log:      /tmp/sglang-serve.log (in container) | ${WORK_DIR}/sglang-serve.log (node)"
    echo "  Debug:          docker exec -it ${CONTAINER} bash"
    echo "  Free device:    docker rm -f ${CONTAINER}"
    # Node-side audit copy: the container may be removed later, WORK_DIR is
    # host-persistent. Best-effort — the serve step may never have run.
    docker cp "${CONTAINER}:/tmp/sglang-serve.log" "${WORK_DIR}/sglang-serve.log" 2>/dev/null || true
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

# The model mount is only needed for the serve test. Mount it read-only when
# the node has the model dir; the serve test (Step 7) exits 1 when it is
# absent rather than silently skipping.
MODEL_MOUNT=""
[[ -d "${MODEL_PATH}" ]] && MODEL_MOUNT="-v ${MODEL_PATH}:${MODEL_PATH}:ro"

docker run -d --name "${CONTAINER}" \
    ${RUN_FLAGS} \
    ${DEVICE_ENV} \
    --shm-size=8g \
    -v "${WORK_DIR}:${WORK_DIR}" \
    ${MODEL_MOUNT} \
    --network host \
    "${RUNTIME_IMAGE}" \
    sleep infinity

log_info "Container started: ${CONTAINER} (${RUNTIME_IMAGE})"

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

# ── Step 3: Single-step install of sglang ───────────────────────────────

log_step "Step 3: Installing sglang==${SGLANG_VERSION}+flagos"

# PYTHONPATH=/opt/triton mirrors the megatron install: pip must see the
# side-dir triton dist-info, or any triton resolution (the vendor torch's
# Requires-Dist, future extras) pulls a fresh generic triton into
# site-packages and the Step 5b matrix diff fails. Runtime switches exported
# BEFORE the install per the playbook.
docker exec "${CONTAINER}" bash -c "
    ${SGLANG_SWITCHES}
    PYTHONPATH=/opt/triton pip install \
        --index-url '${VENDOR_PYPI}' \
        --extra-index-url '${ALIYUN_PYPI}' \
        'sglang==${SGLANG_VERSION}+flagos'
"

log_info "sglang installed:"
docker exec "${CONTAINER}" pip show sglang | grep -E "^(Name|Version|Location)" || true

# ── Step 4: Build + install the sglang_fl plugin (in-container) ─────────

log_step "Step 4: Building + installing sglang_fl plugin (sglang-plugin-FL @ ${PLUGIN_REF})"

# The plugin is not on any index: clone the repo at ${PLUGIN_REF} and build
# the wheel IN the container (the same way the app image build will), not on
# the node. `pip wheel` with PEP 517 isolation pulls the build backend from
# the vendor index + aliyun extra — never pypi.org directly. The result is a
# py3-none-any wheel (pure Python): no compiled ext, no build toolchain.
docker exec "${CONTAINER}" bash -c "
    set -e
    ${SGLANG_SWITCHES}
    rm -rf /tmp/sglang-plugin-FL /tmp/sglang-fl-wheels
    git clone --depth 1 --branch '${PLUGIN_REF}' '${PLUGIN_REPO}' /tmp/sglang-plugin-FL
    mkdir -p /tmp/sglang-fl-wheels
    cd /tmp/sglang-plugin-FL
    pip wheel . --no-deps -w /tmp/sglang-fl-wheels \
        --index-url '${VENDOR_PYPI}' \
        --extra-index-url '${ALIYUN_PYPI}'
    pip install \
        --index-url '${VENDOR_PYPI}' \
        --extra-index-url '${ALIYUN_PYPI}' \
        /tmp/sglang-fl-wheels/sglang_fl-*.whl
    echo ''
    pip show sglang-fl | grep -E '^(Name|Version|Location)'
"

# ── Step 5: AFTER snapshot and compare ──────────────────────────────────

log_step "Step 5: AFTER dependency snapshot"

snapshot | tee "${WORK_DIR}/after.txt"

log_step "Step 5b: Comparing BEFORE vs AFTER"

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

# ── Step 6: Import check ────────────────────────────────────────────────

log_step "Step 6: Import check (sglang + sgl_kernel + sglang_fl)"

# sglang gates flashinfer at import time and sgl_kernel checks its version at
# import — the switches must be exported in THIS shell, not just at install.
docker exec "${CONTAINER}" bash -c '
    '"${COMPILER_GUARD}"'
    '"${SGLANG_SWITCHES}"'
    python3 - <<'"'"'PY'"'"'
import importlib.metadata
import sglang
import sgl_kernel
import sglang_fl

print("sglang imported:", sglang.__file__)
print("sglang version:", importlib.metadata.version("sglang"))
print("sgl_kernel imported:", sgl_kernel.__file__)
print("sglang_fl imported:", sglang_fl.__file__)
PY
'

# ── Step 7: E2E serve (Qwen3-0.6B, 3× chat/completions) ─────────────────

if [[ "$SKIP_SERVE" == true ]]; then
    log_info "Step 7: Skipping serve test (--skip-serve — manual debugging only)"
else
    log_step "Step 7: E2E serve (Qwen3-0.6B, 3× chat/completions)"

    if [[ ! -d "$MODEL_PATH" ]]; then
        log_error "Model not found at: $MODEL_PATH"
        log_error "A serve test needs a real model — refusing to skip. Set MODEL_PATH"
        log_error "(or pass --skip-serve for manual debugging only)."
        exit 1
    fi

    log_info "Starting sglang serve on ${CONTAINER} (this may take several minutes)..."

    docker exec "${CONTAINER}" bash -c "
        ${COMPILER_GUARD}
        ${SGLANG_SWITCHES}
        export SERVE_TIMEOUT=${SERVE_TIMEOUT}
        export SGLANG_PORT=${SGLANG_PORT}

        # flag_gems SQL ConfigCache is shared across compilers: an F-path
        # tuned BLOCK_SIZE_M=8 config is cache-hit by the T path and
        # hard-crashes (PassManager::run failed, playbook §5.4). A fresh
        # container from the image carries at most a bake-time default-compiler
        # db — clear it so this run's kernels tune under the ACTIVE compiler,
        # whatever it is.
        rm -f /root/.flaggems/config_cache/TunedConfig_*.db

        echo ''
        echo 'Starting serve...'
        python3 -m sglang.launch_server '${MODEL_PATH}' \
            --port \${SGLANG_PORT} \
            --mem-fraction-static 0.6 \
            --trust-remote-code \
            --disable-cuda-graph \
            --disable-piecewise-cuda-graph \
            > /tmp/sglang-serve.log 2>&1 &

        SERVE_PID=\$!
        # Poll the log for readiness (up to SERVE_TIMEOUT). Cold-start cost
        # varies by backend (flag_gems first-compile + KV-cache profile), so
        # the window is configurable via --serve-timeout like the vllm script.
        echo 'Waiting for serve to become ready...'
        ready=0
        for i in \$(seq 1 \$((SERVE_TIMEOUT / 5))); do
            if ! kill -0 \${SERVE_PID} 2>/dev/null; then
                echo 'serve process exited during startup'
                break
            fi
            if grep -qE 'Application startup complete|Uvicorn running' /tmp/sglang-serve.log 2>/dev/null; then
                ready=1
                echo \"serve ready after ~\$((i*5))s\"
                break
            fi
            sleep 5
        done
        if [ \"\$ready\" != \"1\" ]; then
            echo 'serve did not become ready in time; last 60 lines of log:'
            tail -60 /tmp/sglang-serve.log 2>/dev/null || true
            kill \${SERVE_PID} 2>/dev/null || true
            exit 1
        fi

        echo ''
        echo 'Sending 3× chat/completions...'
        python3 - <<'PY'
import json, sys, urllib.request

# Single-model server: the model field is a no-op, 'default' is sglang's
# conventional placeholder. First request compiles flag_gems kernels per-shape
# — TIMEOUT is the full SERVE_TIMEOUT budget so cold backends are not clipped.
url = 'http://127.0.0.1:' + '${SGLANG_PORT}' + '/v1/chat/completions'
TIMEOUT = ${SERVE_TIMEOUT}

def check(i, prompt):
    payload = json.dumps({
        'model': 'default',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 144,
        'temperature': 0,
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print('request %d: HTTP %s %s' % (i, e.code, e.reason))
        try:
            print(e.read().decode()[:500])
        except Exception:
            pass
        return False
    except Exception as e:
        print('request %d: failed: %r' % (i, e))
        return False
    usage = body.get('usage') or {}
    ct = usage.get('completion_tokens')
    sb = body.get('sampling_backend') or usage.get('sampling_backend')
    ok = status == 200 and ct == 144 and sb == 'pytorch'
    print('request %d: status=%s completion_tokens=%s sampling_backend=%r -> %s'
          % (i, status, ct, sb, 'OK' if ok else 'FAIL'))
    return ok

results = [
    check(1, 'Write a long paragraph describing the history of computing.'),
    check(2, 'Explain in detail how a transformer model generates text.'),
    check(3, 'Describe the steps of training a large language model.'),
]
if not all(results):
    print('CRITERIA NOT MET: HTTP 200 + completion_tokens=144 + sampling_backend=pytorch on all 3 requests')
    sys.exit(1)
print('ALL 3 chat/completions PASSED (completion_tokens=144, sampling_backend=pytorch)')
PY

        rc=\$?
        kill \${SERVE_PID} 2>/dev/null || true
        exit \$rc
    "

    # Node-side audit copy lives in cleanup() — this line only acknowledges.
    log_info "Serve test done (log: ${WORK_DIR}/sglang-serve.log)"
fi

# ── Summary ─────────────────────────────────────────────────────────────

echo ""
echo "========================================"
echo "Verification Summary"
echo "========================================"
echo "Backend:          ${VENDOR_BACKEND}"
echo "sglang Version:   ${SGLANG_VERSION}+flagos"
echo "Plugin Ref:       ${PLUGIN_REF}"
echo "Compiler:         ${COMPILER:-<runtime default>}"
echo "Container:        ${CONTAINER}"
echo ""
echo "Status:"
docker exec "${CONTAINER}" bash -c "
    ${COMPILER_GUARD}
    echo -n 'sglang: '; python3 -c 'import importlib.metadata, sglang; print(importlib.metadata.version(\"sglang\"))' 2>/dev/null || echo 'FAILED'
    echo -n 'sglang_fl: '; python3 -c 'import importlib.metadata, sglang_fl; print(importlib.metadata.version(\"sglang-fl\"))' 2>/dev/null || echo 'FAILED'
    echo -n 'torch: '; python3 -c 'import torch; print(torch.__version__)' 2>/dev/null || echo 'FAILED'
    echo -n 'flag_gems: '; python3 -c 'import flag_gems; print(flag_gems.__version__)' 2>/dev/null || echo 'FAILED'
"
echo ""
echo "To debug:"
echo "  docker exec -it ${CONTAINER} bash"
echo ""
