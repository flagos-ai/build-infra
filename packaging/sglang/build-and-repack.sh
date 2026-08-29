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
# build-and-repack.sh — Build and repack sglang for one backend
# ============================================================
#
# Usage:
#   build-and-repack.sh metax-maca3.8.1.3
#   build-and-repack.sh ascend-cann9.0.0 --sglang-version 0.5.18
#   build-and-repack.sh metax-maca3.8.1.3 --upload
#   build-and-repack.sh metax-maca3.8.1.3 --rust-version 1.98.0
#
# Options:
#   --sglang-version X.Y.Z  sglang version to build (default: 0.5.18)
#   --rust-version X.Y.Z    Rust toolchain version for the multimodal rust
#                           ext (default: 1.98.0; fetched from the filestore
#                           cache, rustup fallback)
#   --upload                After repacking, twine-upload the +flagos wheels
#                           to the per-vendor PyPI (flagos-pypi-<vendor>).
#                           Opt-in: uploading publishes artifacts, so it never
#                           runs by default. All repacked wheels stay per-vendor
#                           alongside that backend's torch/flag_gems/flagtree —
#                           the wheel is ABI-bound to the vendor image's
#                           (python, arch), and keeping the matched sglang+deps
#                           set on one index avoids split-index fragility on an
#                           sglang version bump.
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
#   - build image flagos-runtime-<vendor>-<backend>:<version>-build
#   - sglang source tarball at flagos-filestore (official source archive —
#     sglang publishes no pip sdist — one architecture-independent tarball
#     serves every backend; see build-sdist.sh)
#   - twine on the host (only when --upload is used)
#
# Build base: sglang builds from the non-CUDA pyproject variant (srt_empty
# base) whose METADATA is torch-free and sglang-kernel-free by construction —
# see docs/sglang-0.5.18/decisions.md. The filestore tarball is the official
# source archive (no pip sdist exists); the non-CUDA variant is switched in
# and runtime_base merged into `dependencies` inside the container via
# merge-runtime-base.py (the same single source of truth build-sdist.sh uses).
# repack.py therefore only stamps the +flagos local version (and downgrades
# Metadata-Version 2.4 → 2.2); no dependency stripping happens (config.yaml
# rules are all empty). --no-recurse skips the recursion pass entirely — with
# zero strip rules it would only do a pointless network resolve of every
# declared runtime dep.
#
# TODO:
#   - Per-backend default sglang_version in configs.yaml
#   - Record empty wheel sha256 in manifest

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

# Upload target.  Everything stays on the per-vendor index: the wheel and its
# runtime deps are ABI-bound to this vendor image's (python, arch), and
# keeping the whole matched set — sglang + its exact transformers/llguidance/
# compressed-tensors — on one index is what makes an sglang version bump safe
# (re-repack regenerates a coherent set; no split-index skew reintroducing a
# torch/sglang-kernel leak).
UPLOAD_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/"

# ptpu vendors (e.g. sunrise) abort in torch at import when no device is
# visible (tangGetDeviceCount failed), so the build container must see /dev.
# Default DOCKER_RUN_FLAGS from build-config.yml run.vendors.<vendor> — the
# same single source verify scripts read — so CI and manual runs get the
# right flags without hardcoding them here. An explicit DOCKER_RUN_FLAGS
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

CONTAINER="sglang-build-${VENDOR}-${BACKEND}"

# ── Clean up previous run ───────────────────────────────────────────────

docker rm -f "$CONTAINER" 2>/dev/null || true
# The build container writes as root into the bind mount; under /tmp's
# sticky bit a non-root runner cannot rm those files, so a stale work dir
# poisons the next run. Delete from inside the image (root) when it is
# available, then tolerate a leftover (the container may not be pullable
# on a first run). Same pattern as vllm build-and-repack.sh.
# Create the dir FIRST as the runner: docker auto-creates a missing
# bind-mount source as root, and a root-owned dir under /tmp's sticky bit
# is then neither rm-able nor mkdir-able by the runner. The docker cleanup
# also chowns the (emptied) dir back to the runner so a stale root-owned
# dir from a crashed manual build self-heals.
mkdir -p "$WORK_DIR" 2>/dev/null || true
docker run --rm -v "${WORK_DIR}:/work" "$BUILD_IMAGE" \
    bash -c "rm -rf /work; chown -R $(id -u):$(id -g) /work" 2>/dev/null || true
rm -rf "$WORK_DIR" 2>/dev/null || true
mkdir -p "$WORK_DIR/output" "$WORK_DIR/cache"

# ── Copy repack files into work dir ─────────────────────────────────────

cp "$SCRIPT_DIR/repack.py" "$SCRIPT_DIR/config.yaml" \
    "$SCRIPT_DIR/merge-runtime-base.py" "$WORK_DIR/"

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
# (rust-extensions = ["multimodal"] in the non-CUDA pyproject variant).
# The rust *toolchain* itself is set up in the build step below — the distro
# apt cargo (1.75 on Ubuntu 24.04) cannot even parse the 0.5.18 workspace
# manifest (resolver = "3" / edition = "2024" need cargo ≥ 1.84 / rustc ≥
# 1.85), so a modern stable is rustup-installed right before the wheel build.
docker exec "$CONTAINER" bash -c "
    set -e
    pip install -i https://mirrors.aliyun.com/pypi/simple \
        'setuptools-scm>=8,<10' 'setuptools-rust>=1.10' wheel \
        > /dev/null 2>&1
"

# Every backend builds the same wheel from the filestore source tarball.
# Note: sglang publishes wheels only — no pip sdist, no GitHub release
# assets — so the filestore tarball is the official source archive
# (sglang-<version>/ with python/ nested at the repo root). The non-CUDA
# pyproject variant (pyproject_other.toml, srt_empty base) is switched in
# and runtime_base merged into `dependencies` inside the container, exactly
# as build-sdist.sh does via merge-runtime-base.py — the single source of
# truth — so the wheel's METADATA is torch-free / sglang-kernel-free by
# construction and carries the full runtime set in Requires-Dist for a
# single-step `pip install sglang==<version>+flagos`. A future sdist-style
# tarball (pyproject.toml at top level) is handled too.
echo "==> Mode: source build (non-CUDA variant)"
SRC_TAR="sglang-${SGLANG_VERSION}.tar.gz"
SRC_URL="${FILESTORE}/sglang/sglang-${SGLANG_VERSION}.tar.gz"
docker exec "$CONTAINER" bash -c "
    set -e
    cd ${WORK_DIR}
    mkdir -p ${WORK_DIR}/src ${WORK_DIR}/out

    # Pull source from filestore
    echo 'Downloading ${SRC_URL} …'
    curl -sL -o ${WORK_DIR}/${SRC_TAR} '${SRC_URL}'
    tar xzf ${WORK_DIR}/${SRC_TAR} -C ${WORK_DIR}/src
    mv ${WORK_DIR}/src/sglang-${SGLANG_VERSION} ${WORK_DIR}/src/sglang
    rm ${WORK_DIR}/${SRC_TAR}

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

    # Rust toolchain for the multimodal rust ext. Guard: if the present
    # cargo can already read the workspace manifest, skip — a -build image
    # that ships a modern cargo is used as-is (never downgrade it with the
    # distro apt package). Ubuntu 24.04's apt cargo (1.75) fails on
    # resolver = "3" / edition = "2024", so fetch a modern toolchain. The
    # official dist tarball is cached on the filestore by
    # cache-rust-toolchain.sh (same pattern as the sglang source tarball —
    # one sha256-verified artifact serves every build; no external CDN at
    # wheel time). Fall back to rustup from static.rust-lang.org only when
    # the tarball is not cached yet, so a fresh filestore never blocks the
    # first build. If the ext is hard-required the wheel build below fails
    # loudly rather than silently skipping (decisions.md documents the rust
    # workspace rides in the source tarball).
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
            echo '    (cache it once with cache-rust-toolchain.sh --upload)'
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
