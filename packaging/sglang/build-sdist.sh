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
# build-sdist.sh — Build the shared sglang source tarball
# ============================================================
#
# sglang publishes wheels only (no pip sdist, no release assets), so we
# build the architecture-independent source tarball once here and upload it
# to flagos-filestore — every per-vendor wheel build consumes the same
# tarball (x86 and ascend aarch64 alike). Built from the non-CUDA pyproject
# variant (pyproject_other.toml, srt_empty base) with runtime_base merged
# into dependencies — see docs/sglang-0.5.18/decisions.md §2.
#
# Usage:
#   build-sdist.sh --version 0.5.18 [--upload]
#
# Options:
#   --version X.Y.Z  sglang version (default: 0.5.18)
#   --upload         Upload the tarball to
#                    https://resource.flagos.net/repository/flagos-filestore/sglang/
#                    Opt-in: publishing is outward-facing, so it never runs
#                    by default.
#
# Env:
#   NEXUS_TOKEN   "user:token" — required with --upload (same secret/format
#                 as upload-nexus.yml).
#   https_proxy   Must be exported for the github clone on target nodes
#                 (work rule 22: proxy config never lives inside the script
#                 or any repo file).
#
# Prerequisites (run this on a target node, not a developer laptop):
#   - git, python3 (with venv support), network to github.com (via proxy)
#     and to the aliyun pypi mirror
#
# Verify gates (the baseline for the shared artifact):
#   - PKG-INFO Version must equal --version — setuptools_scm must resolve
#     the git tag; a 0.0.0.dev0 fallback fails the build loudly.
#   - Requires-Dist must not contain the critical watchlist (torch chain,
#     sglang-kernel, cuda stack, …) — a smoke check mirroring the
#     audit-deps.py watchlist; the authoritative gate re-runs on every wheel
#     at build-and-repack.sh audit time.
#
# TODO:
#   - Record the tarball sha256 in the build manifest

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

SGLANG_VERSION="0.5.18"
UPLOAD=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) SGLANG_VERSION="$2"; shift 2 ;;
        --upload) UPLOAD=true; shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

GIT_TAG="v${SGLANG_VERSION}"
FILESTORE="https://resource.flagos.net/repository/flagos-filestore"
SRC_TAR="sglang-${SGLANG_VERSION}.tar.gz"

WORK_DIR="$(mktemp -d /tmp/sglang-sdist-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Clone the release tag ───────────────────────────────────────────────

echo "==> Cloning sglang ${GIT_TAG} …"
git clone --depth 1 --branch "${GIT_TAG}" \
    https://github.com/sgl-project/sglang.git "${WORK_DIR}/sglang" \
    || { echo "ERROR: github clone failed — export https_proxy on this node (work rule 22)" >&2; exit 1; }

cd "${WORK_DIR}/sglang/python"

# ── Switch to the non-CUDA pyproject variant ────────────────────────────

cp pyproject_other.toml pyproject.toml

# ── pyproject references readme/LICENSE files ───────────────────────────
# The 0.5.x python/ dir lacks README.md / LICENSE (observed in 0.5.10) yet
# pyproject_other.toml declares them — setuptools refuses to build without.
# Copy from the repo root (idempotent).
[[ -f README.md ]] || cp ../README.md .
[[ -f LICENSE ]] || cp ../LICENSE .

# ── Merge runtime_base into dependencies ────────────────────────────────
# So the wheel's Requires-Dist carries the full runtime set for a one-step
# install. Single source of truth: merge-runtime-base.py is shared with
# build-and-repack.sh, so the two paths cannot drift.
python3 "${SCRIPT_DIR}/merge-runtime-base.py" pyproject.toml

# ── Build the sdist ─────────────────────────────────────────────────────

echo "==> Building sdist (${SRC_TAR}) …"
python3 -m venv "${WORK_DIR}/venv"
"${WORK_DIR}/venv/bin/pip" install --quiet \
    -i https://mirrors.aliyun.com/pypi/simple \
    'build' 'setuptools>=70,<78' 'setuptools-scm>=8,<10' \
    'setuptools-rust>=1.10' 'wheel'
# --no-isolation: use exactly the versions installed above. setuptools <78
# keeps the deprecated `license = { file = ... }` form from pyproject_other
# a warning instead of a hard error.
"${WORK_DIR}/venv/bin/python" -m build --sdist --no-isolation \
    --outdir "${WORK_DIR}/dist" .

[[ -f "${WORK_DIR}/dist/${SRC_TAR}" ]] \
    || { echo "ERROR: expected sdist at ${SRC_TAR} but it was not produced" >&2; exit 1; }

# ── Verify the sdist ────────────────────────────────────────────────────

echo "==> Verifying sdist …"
mkdir -p "${WORK_DIR}/verify"
tar xzf "${WORK_DIR}/dist/${SRC_TAR}" -C "${WORK_DIR}/verify"
ROOT_DIR="${WORK_DIR}/verify/sglang-${SGLANG_VERSION}"
PKG_INFO="${ROOT_DIR}/PKG-INFO"

[[ -f "$PKG_INFO" ]] || { echo "ERROR: sdist missing PKG-INFO (package layout changed?)" >&2; exit 1; }
[[ -d "${ROOT_DIR}/sglang" ]] || { echo "ERROR: sdist missing python/sglang/ package" >&2; exit 1; }

ver=$(grep -m1 '^Version:' "$PKG_INFO" | awk '{print $2}')
if [[ "$ver" != "$SGLANG_VERSION" ]]; then
    echo "ERROR: setuptools_scm resolved version '${ver}', expected '${SGLANG_VERSION}'" >&2
    echo "       (clone must be at tag ${GIT_TAG}; check scripts/release/get_version_tag.py output)" >&2
    exit 1
fi

# Requires-Dist smoke check — mirrors audit-deps.py's --watch default
# semantics (trailing '*' = prefix). Keep in sync with that list; the
# wheel-time audit in build-and-repack.sh / sglang-wheel.yml is authoritative.
python3 - "$PKG_INFO" <<'PY'
import sys

watch = [
    "torch", "torchaudio", "torchvision", "torchcodec", "torch-c-dlpack-ext",
    "triton", "sglang-kernel", "cuda-python", "flashinfer*", "flash-attn-4",
    "sgl-deep-gemm", "sgl-deep-ep", "tilelang", "tokenspeed-mla",
    "quack-kernels", "nvidia-*", "numba", "kernels",
    "torch-memory-saver", "torchao", "nvidia-modelopt", "flag-gems",
]
prefixes = [w[:-1] for w in watch if w.endswith("*")]
exact = {w for w in watch if not w.endswith("*")}

hits = []
for ln in open(sys.argv[1]):
    if ln.startswith("Requires-Dist:"):
        name = (ln.split(":", 1)[1].strip()
                  .split(";", 1)[0].split("[", 1)[0].strip().lower()
                  .replace("_", "-"))
        if name in exact or any(name.startswith(p) for p in prefixes):
            hits.append(name)
if hits:
    sys.exit("ERROR: sdist declares critical package(s): "
             + ", ".join(sorted(set(hits))))
PY

sha=$(shasum -a 256 "${WORK_DIR}/dist/${SRC_TAR}" | awk '{print $1}')
size=$(du -h "${WORK_DIR}/dist/${SRC_TAR}" | cut -f1)
echo "  Version:       ${ver}"
echo "  Requires-Dist: $(grep -c '^Requires-Dist:' "$PKG_INFO") packages"
echo "  ${SRC_TAR}:    ${size}, sha256 ${sha}"

# The rust workspace (multimodal rust ext, [tool.sglang] rust-extensions)
# must ride in the sdist for the wheel build to compile it. Warn if absent —
# not fatal here: whether the ext is hard-required is answered at wheel time.
if ! tar tzf "${WORK_DIR}/dist/${SRC_TAR}" \
        | grep -q "^sglang-${SGLANG_VERSION}/rust/"; then
    echo "WARNING: no rust/ workspace in the sdist — the multimodal rust ext"
    echo "         will fail to build at wheel time if it is hard-required."
fi

# ── Upload (opt-in) ─────────────────────────────────────────────────────

if [[ "$UPLOAD" == true ]]; then
    echo ""
    echo "==> Uploading to ${FILESTORE}/sglang/ …"
    : "${NEXUS_TOKEN:?NEXUS_TOKEN (user:token) is required with --upload}"
    curl -f -u "${NEXUS_TOKEN}" --upload-file "${WORK_DIR}/dist/${SRC_TAR}" \
        "${FILESTORE}/sglang/${SRC_TAR}"
    echo "  -> OK"
fi

echo ""
echo "==> Done.  Artifact (deleted with WORK_DIR on exit unless --upload):"
echo "  ${WORK_DIR}/dist/${SRC_TAR}"
echo "  download path used by build-and-repack.sh: ${FILESTORE}/sglang/${SRC_TAR}"
