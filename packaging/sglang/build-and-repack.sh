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
# build-and-repack.sh — Build + repack the sglang wheel for one backend
# ============================================================
#
# Usage:
#   build-and-repack.sh metax-maca3.8.1.3 [--sglang-version 0.5.18]
#                       [--rust-version 1.98.0] [--upload]
#
# Options:
#   --sglang-version X.Y.Z  sglang version (default 0.5.18)
#   --rust-version X.Y.Z    Rust toolchain for the multimodal rust ext
#                           (default 1.98.0; filestore cache, rustup fallback)
#   --upload                twine-upload the repacked wheel to the per-vendor
#                           PyPI (flagos-pypi-<vendor>); publishing is
#                           outward-facing so it never runs by default
#
# Env:
#   STACK_VERSION      stack version for the -build image tag (default: read
#                      from configs.yaml)
#   DOCKER_RUN_FLAGS   extra `docker run` flags; defaults to the vendor's run
#                      flags from .github/build-config.yml (toolkit ?: raw) —
#                      ptpu vendors (e.g. sunrise) need /dev visible at build
#
# Prereqs: docker + harbor access; python3 + pyyaml on the host; the
# flagos-runtime-<vendor>-<backend>:<version>-build image; the shared source
# tarball on the filestore (build-sdist.sh).
#
# Model (srt_empty base, no dep stripping, per-vendor upload, rust cache):
# see docs/sglang-0.5.18/decisions.md; step-by-step: playbook.md.

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <vendor>-<backend> [--sglang-version X.Y.Z] [--upload]" >&2
    exit 1
fi

VENDOR_BACKEND="$1"
shift

SGLANG_VERSION="0.5.18"
RUST_VERSION="1.98.0"
UPLOAD=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --sglang-version) SGLANG_VERSION="$2"; shift 2 ;;
        --rust-version) RUST_VERSION="$2"; shift 2 ;;
        --upload) UPLOAD=true; shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

VENDOR="${VENDOR_BACKEND%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

# ── Paths ───────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/sglang-repack-${VENDOR}-${BACKEND}"

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

BUILD_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR}-${BACKEND}:${STACK_VERSION}-build"
FILESTORE="https://resource.flagos.net/repository/flagos-filestore"

# Per-vendor index: the wheel + its ABI-bound runtime deps form one matched
# set, so a version bump regenerates a coherent set (decisions.md §3).
UPLOAD_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/"

# ptpu vendors (e.g. sunrise) need /dev visible at build. Default flags from
# build-config.yml run.vendors (same source verify scripts read); an
# explicit DOCKER_RUN_FLAGS env wins.
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

CONTAINER="sglang-build-${VENDOR}-${BACKEND}"

# ── Clean up previous run ───────────────────────────────────────────────

docker rm -f "$CONTAINER" 2>/dev/null || true
# The container (root) writes into the bind mount; under /tmp's sticky bit a
# non-root runner cannot rm those files, so delete from inside the image
# (root) first — a stale root-owned work dir poisons the next run (same as
# vllm). Create the dir FIRST as the runner: docker auto-creates a missing
# bind-mount source as root, which is then neither rm-able nor mkdir-able;
# the docker cleanup chowns it back so a stale dir self-heals.
mkdir -p "$WORK_DIR" 2>/dev/null || true
docker run --rm -v "${WORK_DIR}:/work" "$BUILD_IMAGE" \
    bash -c "rm -rf /work; chown -R $(id -u):$(id -g) /work" 2>/dev/null || true
rm -rf "$WORK_DIR" 2>/dev/null || true
mkdir -p "$WORK_DIR/output" "$WORK_DIR/cache"

# ── Copy repack files into work dir ─────────────────────────────────────

cp "$SCRIPT_DIR/../script/repack.py" "$SCRIPT_DIR/config.yaml" \
    "$SCRIPT_DIR/merge-runtime-base.py" "$WORK_DIR/"

# ── Pull source (host-side) ──────────────────────────────────────────────
#
# The source tarball is downloaded and extracted on the host, never inside the
# build container: the container consumes the pristine official tree, so
# `patch` is not a build-image dependency and the wheel carries exactly the
# upstream tag. Per-vendor runtime compatibility (JIT/cudnn/fp8 fallbacks)
# lives in the plugin layer — sglang_fl vendor patches applied at load_plugin —
# not in the wheel (ADR §5.5).

echo "==> Mode: source build (non-CUDA variant)"
SRC_TAR="sglang-${SGLANG_VERSION}.tar.gz"
SRC_URL="${FILESTORE}/sglang/sglang-${SGLANG_VERSION}.tar.gz"
echo "==> Downloading ${SRC_URL} …"
curl -sL -o "${WORK_DIR}/${SRC_TAR}" "${SRC_URL}"
mkdir -p "${WORK_DIR}/src" "${WORK_DIR}/out"
tar xzf "${WORK_DIR}/${SRC_TAR}" -C "${WORK_DIR}/src"
mv "${WORK_DIR}/src/sglang-${SGLANG_VERSION}" "${WORK_DIR}/src/sglang"
rm "${WORK_DIR}/${SRC_TAR}"

# ── Start build container ───────────────────────────────────────────────

echo "==> Image:  ${BUILD_IMAGE}"
echo "==> sglang: ${SGLANG_VERSION}"
echo "==> rust:   ${RUST_VERSION} (filestore cache, rustup fallback)"
echo "==> Output: ${WORK_DIR}/output/"
echo ""

docker pull "$BUILD_IMAGE" > /dev/null 2>&1 || true

docker run -d --name "$CONTAINER" --network host \
    -v "${WORK_DIR}:${WORK_DIR}" \
    ${DOCKER_RUN_FLAGS:-} \
    "$BUILD_IMAGE" sleep infinity

# ── Build + repack ──────────────────────────────────────────────────────

# Ensure build deps — remove once build images include setuptools-scm.
# setuptools-rust is required by the sglang rust extensions
# (rust-extensions = ["multimodal"]); the rust *toolchain* is set up in the
# build step below.
docker exec "$CONTAINER" bash -c "
    set -e
    pip install -i https://mirrors.aliyun.com/pypi/simple \
        'setuptools-scm>=8,<10' 'setuptools-rust>=1.10' wheel \
        > /dev/null 2>&1
"

# Every backend builds the same wheel from the filestore source tarball
# (sglang ships no pip sdist). The tarball was already pulled on the host
# (above); in the container only the non-CUDA pyproject variant
# (srt_empty base) is switched in and runtime_base merged into `dependencies`,
# exactly as build-sdist.sh does — single source of truth, the wheel's
# METADATA is torch-free by construction (decisions.md §2).
docker exec "$CONTAINER" bash -c "
    set -e
    cd ${WORK_DIR}

    # Locate the python package dir. The official source archive nests it
    # under python/; a built sdist-style tarball would have pyproject.toml
    # at the top (already merged) — detect both.
    cd ${WORK_DIR}/src/sglang
    if [[ -f python/pyproject_other.toml ]]; then
        cd python
        cp pyproject_other.toml pyproject.toml
        # pyproject_other.toml declares readme/LICENSE files the 0.5.x
        # python/ dir does not ship; copy from the repo root (idempotent).
        [[ -f README.md ]] || [[ ! -f ../README.md ]] || cp ../README.md .
        [[ -f LICENSE ]] || [[ ! -f ../LICENSE ]] || cp ../LICENSE .
    elif [[ -f pyproject_other.toml ]]; then
        cp pyproject_other.toml pyproject.toml
    fi
    # Merge runtime_base into dependencies (no-op if already merged — the
    # rewrite is idempotent). Shared with build-sdist.sh, cannot drift.
    python3 ${WORK_DIR}/merge-runtime-base.py pyproject.toml

    # Rust toolchain for the multimodal rust ext. Skip if the present cargo
    # already reads the workspace manifest — never downgrade a -build image
    # with the distro apt cargo (1.75 on Ubuntu 24.04 fails on resolver="3" /
    # edition="2024"). Official dist tarball cached on the filestore (no
    # external CDN at wheel time); rustup from static.rust-lang.org is the
    # fallback for a triple missing from the filestore (decisions.md §5.6).
    # A hard-required ext fails the build loudly rather than silently
    # skipping.
    if ! cargo metadata --format-version 1 --no-deps \
            --manifest-path ${WORK_DIR}/src/sglang/rust/Cargo.toml >/dev/null 2>&1; then
        TRIPLE=\"\$(uname -m)\"
        case \"\${TRIPLE}\" in
            x86_64) TRIPLE=x86_64-unknown-linux-gnu ;;
            aarch64) TRIPLE=aarch64-unknown-linux-gnu ;;
        esac
        RUST_TAR=\"rust-${RUST_VERSION}-\${TRIPLE}.tar.xz\"
        if curl -fsSL -o /tmp/\${RUST_TAR} \
                \"${FILESTORE}/rust/\${RUST_TAR}\" 2>/dev/null; then
            echo '==> Installing cached Rust toolchain from the filestore …'
            tar xJf /tmp/\${RUST_TAR} -C /tmp
            (cd /tmp/rust-${RUST_VERSION}-\${TRIPLE} \
                && ./install.sh --prefix=/opt/rust --without=rust-docs > /dev/null)
            export PATH=\"/opt/rust/bin:\${PATH}\"
        else
            echo '==> Rust tarball not cached on the filestore — falling back to rustup …'
            curl -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh
            sh /tmp/rustup-init.sh -y --profile minimal \
                --default-toolchain stable --no-modify-path > /dev/null 2>&1
            export PATH=\"\${HOME}/.cargo/bin:\${PATH}\"
        fi
        cargo --version
    fi

    # Build wheel (srt_empty base; dependencies now carry the full
    # runtime_base set). The official source archive has no .git, so
    # setuptools_scm cannot resolve the version from a tag — pin it with
    # SETUPTOOLS_SCM_PRETEND_VERSION (verified against the wheel filename
    # below, mirroring the sdist PKG-INFO gate).
    MAX_JOBS=\$(nproc) \
        SETUPTOOLS_SCM_PRETEND_VERSION=${SGLANG_VERSION} \
        pip wheel --no-build-isolation --no-deps -w ${WORK_DIR}/out .

    # Version gate: the wheel must be the requested sglang version. A
    # setuptools_scm 0.0.0.dev0 fallback would fail this loudly.
    wheel=\$(ls ${WORK_DIR}/out/sglang-*.whl)
    case \"\${wheel}\" in
        */sglang-${SGLANG_VERSION}-*) ;;
        *) echo \"ERROR: wheel version mismatch — got \$(basename \"\${wheel}\"), expected sglang-${SGLANG_VERSION}-*\" >&2; exit 1 ;;
    esac
    echo \"  wheel: \$(basename \"\${wheel}\")\"

    echo '==> Repacking …'
    cd ${WORK_DIR}
    python3 ${WORK_DIR}/repack.py --no-recurse ${WORK_DIR}/out/sglang-*.whl
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
