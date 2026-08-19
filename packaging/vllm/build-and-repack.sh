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
# build-and-repack.sh — Build and repack vllm for one backend
# ============================================================
#
# Usage:
#   build-and-repack.sh metax-maca3.7.2.1
#   build-and-repack.sh nvidia-cuda12.8 --vllm-version 0.25.1
#   build-and-repack.sh mthreads-musa5.2.0 --upload
#
# Options:
#   --vllm-version X.Y.Z   vLLM version to build (default: 0.20.2)
#   --upload               After repacking, twine-upload the +flagos wheels
#                          to the per-vendor PyPI (flagos-pypi-<vendor>).
#                          Opt-in: uploading publishes artifacts, so it never
#                          runs by default. All repacked wheels stay per-vendor
#                          alongside that backend's torch/flag_gems/flagtree —
#                          the binary deps (opencv, xgrammar) are ABI-bound to
#                          the vendor image's (python, arch), and keeping the
#                          matched vllm+deps set on one index avoids split-index
#                          fragility on a vllm version bump.
#
# Env:
#   STACK_VERSION        Override the stack version read from configs.yaml
#                        (used for the build image tag).
#   DOCKER_RUN_FLAGS     Extra `docker run` flags for the build container.
#                        ptpu vendors (e.g. sunrise) abort in torch at import
#                        when no device is visible (tangGetDeviceCount failed),
#                        so the build container must see /dev:
#                        DOCKER_RUN_FLAGS="--privileged -v /dev:/dev"
#
# Prerequisites:
#   - Docker with harbor.baai.ac.cn access
#   - python3 + pyyaml on the host (for reading configs.yaml)
#   - build image flagos-runtime-<vendor>-<backend>:<version>-build
#   - vllm source tarball at flagos-filestore (for empty-mode backends)
#   - twine on the host (only when --upload is used)
#
# TODO:
#   - Per-backend default vllm_version in configs.yaml
#   - Record empty wheel sha256 in manifest

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <vendor>-<backend> [--vllm-version X.Y.Z] [--upload]" >&2
    exit 1
fi

VENDOR_BACKEND="$1"
shift

VLLM_VERSION="0.20.2"
UPLOAD=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --vllm-version) VLLM_VERSION="$2"; shift 2 ;;
        --upload) UPLOAD=true; shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

VENDOR="${VENDOR_BACKEND%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

# ── Paths ───────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/vllm-repack-${VENDOR}-${BACKEND}"

# ── Read stack version from configs.yaml ────────────────────────────────

# Try to read version from configs.yaml relative to the script, then from env.
if [[ -n "${STACK_VERSION:-}" ]]; then
    true  # already set via env
elif [[ -f "${SCRIPT_DIR}/../configs.yaml" ]]; then
    STACK_VERSION=$(python3 -c "
import yaml
with open('${SCRIPT_DIR}/../configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")
else
    echo "ERROR: STACK_VERSION not set and configs.yaml not found" >&2
    exit 1
fi

BUILD_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR}-${BACKEND}:${STACK_VERSION}-build"
FILESTORE="https://resource.flagos.net/repository/flagos-filestore"

# Upload target.  Everything stays on the per-vendor index: the binary deps
# (opencv, xgrammar) are ABI-bound to this vendor image's (python, arch), and
# keeping the whole matched set — vllm + its exact xgrammar/opencv/compressed-
# tensors — on one index is what makes a vllm version bump safe (re-repack
# regenerates a coherent set; no split-index skew reintroducing the torch/
# triton leak).
UPLOAD_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/"

CONTAINER="vllm-build-${VENDOR}-${BACKEND}"

# ── Clean up previous run ───────────────────────────────────────────────

docker rm -f "$CONTAINER" 2>/dev/null || true
# The build container writes as root into the bind mount; under /tmp's
# sticky bit a non-root runner cannot rm those files, so a stale work dir
# poisons the next run. Delete from inside the image (root) when it is
# available, then tolerate a leftover (the container may not be pullable
# on a first run). Same pattern as vllm-plugin-wheel.yml's cleanup step.
# Create the dir FIRST as the runner: docker auto-creates a missing
# bind-mount source as root, and a root-owned dir under /tmp's sticky bit
# is then neither rm-able nor mkdir-able by the runner (run 32265302280).
# The docker cleanup also chowns the (emptied) dir back to the runner so a
# stale root-owned dir from a crashed manual build self-heals.
mkdir -p "$WORK_DIR" 2>/dev/null || true
docker run --rm -v "${WORK_DIR}:/work" "$BUILD_IMAGE" \
    bash -c "rm -rf /work; chown -R $(id -u):$(id -g) /work" 2>/dev/null || true
rm -rf "$WORK_DIR" 2>/dev/null || true
mkdir -p "$WORK_DIR/output" "$WORK_DIR/cache"

# ── Copy repack files into work dir ─────────────────────────────────────

cp "$SCRIPT_DIR/repack.py" "$SCRIPT_DIR/config.yaml" "$WORK_DIR/"

# ── Start build container ───────────────────────────────────────────────

echo "==> Image:  ${BUILD_IMAGE}"
echo "==> vllm:   ${VLLM_VERSION}"
echo "==> Output: ${WORK_DIR}/output/"
echo ""

docker pull "$BUILD_IMAGE" > /dev/null 2>&1 || true

docker run -d --name "$CONTAINER" --network host \
    -v "${WORK_DIR}:${WORK_DIR}" \
    ${DOCKER_RUN_FLAGS:-} \
    "$BUILD_IMAGE" sleep infinity

# ── Build + repack ──────────────────────────────────────────────────────

# Ensure build deps — remove once build images include setuptools-scm
# setuptools-rust is required by vllm >= 0.24.0 (Rust frontend components);
# without cargo the optional rust extensions are skipped, not fatal.
docker exec "$CONTAINER" bash -c "
    pip install -i https://mirrors.aliyun.com/pypi/simple \
        'setuptools-scm>=8,<10' 'setuptools-rust>=1.9.0' wheel \
        > /dev/null 2>&1
"

if [[ "$VENDOR" = "nvidia" ]]; then
    echo "==> Mode: standard (pip download)"
    docker exec "$CONTAINER" bash -c "
        set -e
        cd ${WORK_DIR}
        mkdir -p ${WORK_DIR}/empty
        pip download --no-deps --dest ${WORK_DIR}/empty \
            'vllm==${VLLM_VERSION}' \
            -i https://mirrors.aliyun.com/pypi/simple/
        echo '==> Repacking …'
        python3 ${WORK_DIR}/repack.py ${WORK_DIR}/empty/vllm-*.whl
    "
else
    echo "==> Mode: empty (build from source)"
    SRC_TAR="vllm-${VLLM_VERSION}.tar.gz"
    SRC_URL="${FILESTORE}/vllm/vllm-${VLLM_VERSION}.tar.gz"
    docker exec "$CONTAINER" bash -c "
        set -e
        cd ${WORK_DIR}
        mkdir -p ${WORK_DIR}/src ${WORK_DIR}/empty

        # Pull source from filestore
        echo 'Downloading ${SRC_URL} …'
        curl -sL -o ${WORK_DIR}/${SRC_TAR} '${SRC_URL}'
        tar xzf ${WORK_DIR}/${SRC_TAR} -C ${WORK_DIR}/src
        mv ${WORK_DIR}/src/vllm-${VLLM_VERSION} ${WORK_DIR}/src/vllm
        rm ${WORK_DIR}/${SRC_TAR}

        # Build empty wheel
        cd ${WORK_DIR}/src/vllm
        VLLM_TARGET_DEVICE=empty MAX_JOBS=\$(nproc) \
            pip wheel --no-build-isolation --no-deps -w ${WORK_DIR}/empty .

        echo '==> Repacking …'
        cd ${WORK_DIR}
        python3 ${WORK_DIR}/repack.py ${WORK_DIR}/empty/vllm-*.whl
    "
fi

# ── Report ──────────────────────────────────────────────────────────────

echo ""
echo "==> Done.  Output:"
ls -lh "$WORK_DIR/output/" | sed 's/^/  /'

# ── Upload (opt-in) ──────────────────────────────────────────────────────

# Runs on the host: WORK_DIR is bind-mounted, so the repacked wheels are
# already visible outside the container. Publishing to the vendor PyPI is
# outward-facing, so it only happens when --upload is passed.
if [[ "$UPLOAD" == true ]]; then
    echo ""
    echo "==> Uploading to ${UPLOAD_PYPI} …"
    command -v twine > /dev/null || pip install -q twine
    twine upload --repository-url "${UPLOAD_PYPI}" "${WORK_DIR}/output/"*.whl
fi

echo ""
echo "Container kept: ${CONTAINER}"
echo "  docker rm -f ${CONTAINER}   # when done"
