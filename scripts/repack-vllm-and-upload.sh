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
# repack-vllm-and-upload.sh — Build, repack, and upload vllm for any backend
# ============================================================
#
# Usage:
#   ./repack-vllm-and-upload.sh --vendor <vendor> --backend <backend> [--vllm-version X.Y.Z]

set -euo pipefail

VENDOR=""
BACKEND=""
VLLM_VERSION="0.20.2"
SKIP_UPLOAD=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --vendor) VENDOR="$2"; shift 2 ;;
        --backend) BACKEND="$2"; shift 2 ;;
        --vllm-version) VLLM_VERSION="$2"; shift 2 ;;
        --skip-upload) SKIP_UPLOAD=true; shift ;;
        --help)
            echo "Usage: $0 --vendor <vendor> --backend <backend> [options]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$VENDOR" || -z "$BACKEND" ]] && { echo "Error: --vendor and --backend are required"; exit 1; }

VENDOR_BACKEND="${VENDOR}-${BACKEND}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/vllm-repack-${VENDOR}-${BACKEND}"
FILESTORE="https://resource.flagos.net/repository/flagos-filestore"
VENDOR_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/"

STACK_VERSION=$(python3 -c "
import yaml
with open('${SCRIPT_DIR}/../configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")

BUILD_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR_BACKEND}:${STACK_VERSION}-build"
CONTAINER="vllm-repack-${VENDOR}-${BACKEND}"

echo "========================================"
echo "vLLM Repack and Upload"
echo "Vendor: $VENDOR | Backend: $BACKEND | Version: $VLLM_VERSION"
echo "========================================"

# Cleanup
trap 'docker rm -f "${CONTAINER}" 2>/dev/null || true' EXIT

# Prepare
rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"/{src,empty,output,cache}
cp "${SCRIPT_DIR}/../vllm-repack/repack.py" "${SCRIPT_DIR}/../vllm-repack/config.yaml" "${WORK_DIR}/"

# Start container
docker rm -f "${CONTAINER}" 2>/dev/null || true
docker pull "${BUILD_IMAGE}" > /dev/null 2>&1 || true
docker run -d --name "${CONTAINER}" -v "${WORK_DIR}:${WORK_DIR}" --network host "${BUILD_IMAGE}" sleep infinity

# Download source
echo "==> Downloading vllm source..."
SRC_TAR="vllm-${VLLM_VERSION}.tar.gz"
docker exec "${CONTAINER}" bash -c "
    cd ${WORK_DIR}
    curl -sL -o ${SRC_TAR} '${FILESTORE}/vllm/${SRC_TAR}'
    tar xzf ${SRC_TAR} -C src/ && mv src/vllm-${VLLM_VERSION} src/vllm
    rm ${SRC_TAR}
"

# Build empty wheel
echo "==> Building empty wheel..."
docker exec "${CONTAINER}" bash -c "
    # Find all MUSA-related libraries
    echo '=== Searching for MUSA libraries ==='
    find /usr/local -name 'libmusa*.so*' -o -name 'libmusart*.so*' 2>/dev/null

    # Setup library path - prefer real libs over stubs
    for libdir in /usr/local/musa-*/lib /usr/local/musa/lib; do
        if [ -d \"\${libdir}\" ]; then
            export LD_LIBRARY_PATH=\${libdir}:\${LD_LIBRARY_PATH}
        fi
        # Only add stubs if no real lib found
        if [ -d \"\${libdir}/stubs\" ] && [ ! -f \"\${libdir}/libmusa.so\" ]; then
            export LD_LIBRARY_PATH=\${libdir}/stubs:\${LD_LIBRARY_PATH}
        fi
    done

    # Check if we need to use stub library with proper setup
    if [ -f /usr/local/musa-5.2.0/lib/stubs/libmusa.so ] && [ ! -f /usr/local/musa-5.2.0/lib/libmusa.so ]; then
        # Copy stub lib to main lib dir (stubs may need special handling)
        cp /usr/local/musa-5.2.0/lib/stubs/libmusa.so /usr/local/musa-5.2.0/lib/libmusa.so 2>/dev/null || true
        ln -sf libmusa.so /usr/local/musa-5.2.0/lib/libmusa.so.1 2>/dev/null || true
        ldconfig 2>/dev/null || true
    fi

    echo \"LD_LIBRARY_PATH: \$LD_LIBRARY_PATH\"

    # Test torch import (may fail with stubs, try anyway)
    python3 -c 'import torch; print(\"Torch OK:\", torch.__version__)' 2>&1 || echo 'Torch needs real MUSA driver'

    # Try to build anyway - VLLM_TARGET_DEVICE=empty may not need full torch
    cd ${WORK_DIR}/src/vllm
    pip install -q 'setuptools-scm>=8,<10' wheel 2>/dev/null || true
    export VLLM_TARGET_DEVICE=empty
    export MAX_JOBS=\$(nproc)
    # Use --no-build-isolation to use system torch
    pip wheel --no-build-isolation --no-deps -w ${WORK_DIR}/empty . 2>&1 | tail -20
"

# Check if wheel was built
if ! docker exec "${CONTAINER}" bash -c "ls ${WORK_DIR}/empty/vllm-*.whl 2>/dev/null"; then
    echo "Error: Failed to build wheel."
    docker exec "${CONTAINER}" bash -c "
        echo '=== Library files ==='
        find /usr/local/musa* -name '*.so*' 2>/dev/null | head -20
    "
    exit 1
fi

# Repack (now handled by repack.py with +flagos suffix)
echo "==> Repacking wheel..."
docker exec "${CONTAINER}" bash -c "cd ${WORK_DIR} && python3 repack.py empty/vllm-*.whl"

# Show results
echo "==> Output:"
docker exec "${CONTAINER}" bash -c "ls -lh ${WORK_DIR}/output/"

# Upload
if [[ "$SKIP_UPLOAD" != true ]]; then
    echo "==> Uploading to ${VENDOR_PYPI}..."
    command -v twine > /dev/null || pip install -q twine
    twine upload --repository-url "${VENDOR_PYPI}" "${WORK_DIR}/output/"*.whl
fi

echo "==> Done. Work dir: ${WORK_DIR}"
