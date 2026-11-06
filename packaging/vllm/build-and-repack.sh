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
#                          runs by default. See the upload target below for
#                          why the whole set stays on one index.
#
# Env:
#   STACK_VERSION        Override the stack version read from configs.yaml
#                        (used for the build image tag).
#   DOCKER_RUN_FLAGS     Extra `docker run` flags for the build container.
#                        Defaults to the vendor's run flags from
#                        .github/build-config.yml (toolkit ?: raw) — ptpu
#                        vendors (e.g. sunrise) abort in torch at import when
#                        no device is visible (tangGetDeviceCount failed), so
#                        their build container must see /dev. An explicit env
#                        still overrides the default.
#
# Prerequisites:
#   - Docker with harbor.baai.ac.cn access
#   - python3 + pyyaml on the host (for reading configs.yaml)
#   - runtime image flagos-runtime-<vendor>-<backend>:<version>
#   - vllm source tarball at flagos-filestore (all backends build empty mode)
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

# The vendor is the first dash-separated segment, not everything before the
# last one: backend keys carry dashes of their own (ascend-cann9.0.0-910c), and
# `%-*` turns that one into the vendor "ascend-cann9.0.0", i.e. an image ref
# that does not exist and a pypi index that is not the backend's.
VENDOR="${VENDOR_BACKEND%%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

# ── Paths ───────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/vllm-repack-${VENDOR}-${BACKEND}"

# ── Read stack version from configs.yaml ────────────────────────────────

# Try to read version from configs.yaml relative to the script, then from env.
if [[ -n "${STACK_VERSION:-}" ]]; then
    true  # already set via env
elif [[ -f "${SCRIPT_DIR}/../../configs.yaml" ]]; then
    STACK_VERSION=$(python3 -c "
import yaml
with open('${SCRIPT_DIR}/../../configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")
else
    echo "ERROR: STACK_VERSION not set and configs.yaml not found" >&2
    exit 1
fi

BUILD_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR}-${BACKEND}:${STACK_VERSION}"
FILESTORE="https://resource.flagos.net/repository/flagos-filestore"

# Upload target.  The whole repacked set — vllm plus the exact
# xgrammar/opencv/compressed-tensors it was repacked against — goes on the
# vendor index, because the top-level wheel pins those deps to `==<ver>+flagos`
# and a local version is satisfyable only by an index that carries it. The
# public fallback serves only upstream versions, so splitting the set would
# leave that pin unsatisfiable. (Same bytes do appear on other vendors'
# indexes; what the index provides here is the resolver's entry point, not
# isolation.)
UPLOAD_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/"

# ptpu vendors (e.g. sunrise) abort in torch at import when no device is
# visible (tangGetDeviceCount failed), so the build container must see /dev.
# Default DOCKER_RUN_FLAGS from build-config.yml run.vendors.<vendor> — the
# same single source verify-vllm-backend.sh reads — so CI and manual runs get
# the right flags without hardcoding them here. An explicit DOCKER_RUN_FLAGS
# env still wins. (pyyaml is required on the host anyway for configs.yaml.)
if [[ -z "${DOCKER_RUN_FLAGS:-}" ]]; then
    DOCKER_RUN_FLAGS=$(python3 -c "
import yaml
with open('${SCRIPT_DIR}/../../.github/build-config.yml') as f:
    config = yaml.safe_load(f)
vendor = '${VENDOR}'
vendor_config = config.get('run', {}).get('vendors', {}).get(vendor, {})
toolkit = vendor_config.get('toolkit', '')
raw = vendor_config.get('raw', '')
print(toolkit if toolkit else raw)
")
fi

# Outbound access on some runner nodes (the ascend ones) is proxy-only: the
# runner exports HTTP(S)_PROXY and nothing resolves without them — pip dies on
# NameResolutionError for both Aliyun and the internal index. Relay whatever the
# runner has, verbatim, into the steps that reach the network; the verify
# script relays the same set. no_proxy is passed as-is rather than extended:
# only the runner knows which endpoints are internal.
PROXY_ENV_ARGS=()
for _proxy_var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    if [[ -n "${!_proxy_var:-}" ]]; then
        PROXY_ENV_ARGS+=(-e "${_proxy_var}")
    fi
done

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

cp "$SCRIPT_DIR/../script/repack.py" "$SCRIPT_DIR/config.yaml" "$WORK_DIR/"

# ── Pull + patch source (host-side) ─────────────────────────────────────
#
# The source tarball is downloaded, extracted and patched on the host, never
# inside the build container: the container consumes an already-patched tree,
# so `patch` is not a build-image dependency and the applied changes stay
# where the build is audited (user constraint: no patching inside containers;
# mirrors packaging/sglang's mechanism).

# Every backend — nvidia included — builds the same empty wheel
# (VLLM_TARGET_DEVICE=empty) from the filestore source tarball. The former
# nvidia-only "standard" mode (pip download of the official wheel) was retired
# 2026-08-23 when nvidia unified onto the empty build ("都走统一个模式").
# The app image installs the repacked +flagos wheel single-step, so the empty
# wheel is what every backend's app-image verification uses.
echo "==> Mode: empty (build from source)"
SRC_TAR="vllm-${VLLM_VERSION}.tar.gz"
SRC_URL="${FILESTORE}/vllm/vllm-${VLLM_VERSION}.tar.gz"
echo "==> Downloading ${SRC_URL} …"
curl -sL -o "${WORK_DIR}/${SRC_TAR}" "${SRC_URL}"
mkdir -p "${WORK_DIR}/src" "${WORK_DIR}/empty"
tar xzf "${WORK_DIR}/${SRC_TAR}" -C "${WORK_DIR}/src"
mv "${WORK_DIR}/src/vllm-${VLLM_VERSION}" "${WORK_DIR}/src/vllm"
rm "${WORK_DIR}/${SRC_TAR}"

# Universal source patches (patches/*.patch), if any. GNU patch ignores the
# license-header preamble before the first `---` line; hunks are generated by
# `diff -u` from the pristine tarball source, so a hunk failing here means the
# source tarball drifted — fail loudly rather than ship an unpatched wheel.
if [[ -d "$SCRIPT_DIR/patches" ]]; then
    if ! command -v patch >/dev/null 2>&1; then
        echo 'ERROR: patch(1) not found on host' >&2
        exit 1
    fi
    for p in "$SCRIPT_DIR"/patches/*.patch; do
        echo "==> Applying $(basename "${p}") …"
        patch -d "${WORK_DIR}/src/vllm" -p1 < "${p}"
    done
fi

# ── Start build container ───────────────────────────────────────────────

echo "==> Image:  ${BUILD_IMAGE}"
echo "==> vllm:   ${VLLM_VERSION}"
echo "==> Output: ${WORK_DIR}/output/"
echo ""

docker pull "$BUILD_IMAGE" > /dev/null 2>&1 || true

# Some vendor toolkits (e.g. enflame) already carry `--network host` in their
# run flags; adding it again makes docker abort with "network host is
# specified multiple times" (run 33592252375), so only inject it when the
# flags do not name a network.
if [[ " ${DOCKER_RUN_FLAGS:-} " != *" --network "* ]]; then
    DOCKER_RUN_FLAGS="${DOCKER_RUN_FLAGS:-} --network host"
fi

docker run -d --name "$CONTAINER" \
    -v "${WORK_DIR}:${WORK_DIR}" \
    ${DOCKER_RUN_FLAGS:-} \
    "${PROXY_ENV_ARGS[@]}" \
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

# Source was pulled + patched on the host above; here the container only
# builds the empty wheel and repacks it.
docker exec "$CONTAINER" bash -c "
    set -e
    cd ${WORK_DIR}/src/vllm

    # Build empty wheel
    VLLM_TARGET_DEVICE=empty MAX_JOBS=\$(nproc) \
        pip wheel --no-build-isolation --no-deps -w ${WORK_DIR}/empty .

    echo '==> Repacking …'
    cd ${WORK_DIR}
    python3 ${WORK_DIR}/repack.py ${WORK_DIR}/empty/vllm-*.whl
"

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
