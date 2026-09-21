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
#
# Verify a FlagCX builder image by compiling one backend's device bitcode in it.
#
# Usage:
#   verify-flagcx-builder.sh --backend nvidia-cuda13.3 --ref <sha>
#
# Options:
#   --backend KEY   backend from backends.yaml (required)
#   --ref REF       FlagCX git ref to build the device bitcode from (required)
#   --repo URL      FlagCX repository to clone from
#   --image REF     image to verify (default: the ref the row publishes)
#   --keep          leave the container behind for inspection
#   -h, --help      this text
#
# The acceptance test is the build, not `docker image inspect`: an image that
# exists says the apt step and the tarball extraction ran, while what this row is
# published for is that the toolchain it carries compiles *this* row's device
# bitcode — clang >= 22 against that row's CUDA headers, the curand header clang's
# CUDA wrapper force-includes, and the comm-traits branch the row's .so takes.
# So the verification clones a ref in and runs the make the wheel line will run.
# `check_public_symbols` is a prerequisite of that target, so the 152 public
# symbols of bindings/ir/public_symbols.txt are already asserted by it — and by
# the .ll it reads, which is why the assertions below are about the artifact
# rather than about the symbol list.
#
# No device flags are passed, unlike verify-flagcx-wheel.sh: nothing here opens a
# device. The bitcode is compiled with --cuda-device-only, no vendor library is
# loaded, and nvcc is only asked for its version. A node that can run the image
# can run this.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"

OPT_BACKEND=""
OPT_REF=""
OPT_REPO="https://github.com/flagos-ai/FlagCX.git"
OPT_IMAGE=""
KEEP=0

usage() { sed -n '18,27p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

fail() {
    echo "verify-flagcx-builder.sh: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend)  OPT_BACKEND="${2:?--backend needs a key}"; shift 2 ;;
        --ref)      OPT_REF="${2:?--ref needs a value}"; shift 2 ;;
        --repo)     OPT_REPO="${2:?--repo needs a URL}"; shift 2 ;;
        --image)    OPT_IMAGE="${2:?--image needs a ref}"; shift 2 ;;
        --keep)     KEEP=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *)          echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ -n "$OPT_BACKEND" ]] || fail "--backend is required: the row is what names the arch and the comm-traits branch"
[[ -n "$OPT_REF" ]] \
    || fail "--ref is required: the bitcode is built from a FlagCX checkout, and a moving ref would make the artifact unverifiable"

cd "$REPO_ROOT"

# Captured into a variable rather than inlined: `set -e` does not see a failure
# inside eval's command substitution, so an inline one would let the script run
# on with every DEB_* empty.
INPUTS="$(python3 packaging/flagcx/flagcx-config.py --build-inputs "$OPT_BACKEND" --channel builder)"
set -a
eval "$INPUTS"
set +a

IMAGE="${OPT_IMAGE:-$DEB_BUILDER_IMAGE}"
[[ -n "$IMAGE" ]] \
    || fail "$OPT_BACKEND: the row publishes no builder image ref; see flagcx-config.py --check --channel builder"
[[ -n "$DEB_BITCODE_ARCH" && -n "$DEB_BITCODE_ADAPTOR_FLAG" ]] \
    || fail "$OPT_BACKEND: no bitcode_arch/bitcode_adaptor_flag, so there is no device bitcode to verify"

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE" \
    || fail "$IMAGE: not built here and not pullable"

# The node's proxy, relayed the way the build relays it: the clone is the one
# step that leaves the node.
PROXY_ENV=()
for pair in http_proxy:HTTP_PROXY https_proxy:HTTPS_PROXY no_proxy:NO_PROXY; do
    lower="${pair%%:*}"; upper="${pair##*:}"
    value="$(printenv "$lower" || true)"
    [ -n "$value" ] || value="$(printenv "$upper" || true)"
    if [ -n "$value" ]; then
        export "${lower}=${value}"
        PROXY_ENV+=(-e "$lower")
    fi
done

CONTAINER="flagcx-builder-verify-$$"
cleanup() {
    local rc=$?
    if (( KEEP )); then
        echo ">>> --keep: $CONTAINER is still running"
    else
        docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    fi
    if (( rc != 0 )); then
        echo ">>> verification failed (rc=$rc); re-run with --keep to inspect" >&2
    fi
}
trap cleanup EXIT

echo ">>> $OPT_BACKEND: $IMAGE at $DEB_BITCODE_ARCH, $DEB_BITCODE_ADAPTOR_FLAG"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
# --network host: the clone is the container's only network use, and the default
# bridge on the runners intermittently cannot open a TCP connection to github.com
# while the host can (measured on metax124 for the wheel line).
docker run -d --name "$CONTAINER" --network host "${PROXY_ENV[@]}" "$IMAGE" sleep infinity >/dev/null

docker exec -i \
    -e BACKEND="$DEB_NAME" -e IMAGE="$IMAGE" \
    -e FLAGCX_REPO="$OPT_REPO" -e FLAGCX_REF="$OPT_REF" \
    -e BITCODE_ARCH="$DEB_BITCODE_ARCH" \
    -e ADAPTOR_FLAG="$DEB_BITCODE_ADAPTOR_FLAG" \
    -e MAKE_ENV="$DEB_MAKE_ENV" \
    "$CONTAINER" bash -euo pipefail -s <<'IN_CONTAINER'
fail() { echo "$BACKEND: $*" >&2; exit 1; }

# Resolved from PATH because that is how the Makefile resolves it (`CLANG ?=
# clang`, and the other three the same way). An absolute path here would verify a
# compiler the build would not have found — which is the whole point of putting
# the toolchain on PATH in the image rather than naming it at the call site.
clang_bin="$(command -v clang || true)"
[ -n "$clang_bin" ] || fail "no clang on PATH — the image carries no device compiler"
for tool in opt llvm-as llvm-dis; do
    command -v "$tool" >/dev/null || fail "no $tool on PATH — the LLVM extraction is incomplete"
done

major="$(clang --version | sed -n 's/.*clang version \([0-9][0-9]*\).*/\1/p' | head -n1)"
[ -n "$major" ] || fail "cannot read a version out of: $(clang --version | head -n1)"
# CUDA 13 removed texture_fetch_functions.h and CUDA 13.2's math_functions.h
# expects the compiler to define _NV_RSQRT_SPECIFIER; both fixes land in LLVM 22.
# Measured: clang-20 and clang-21 compile no device bitcode for CUDA 13.3.
[ "$major" -ge 22 ] \
    || fail "clang $major at $clang_bin — CUDA 13's device headers need 22 or newer"

# The row's own device root and CCL root, from the make_env every other FlagCX
# build already takes. An unset DEVICE_HOME is not inert here: the Makefile's
# ladder defaults it to /usr/local/cuda, so a row whose SDK lives elsewhere would
# compile against nothing and fail on a header rather than on the reason.
# shellcheck disable=SC2086
export $MAKE_ENV
: "${DEVICE_HOME:?the row's make_env states no DEVICE_HOME}"
: "${CCL_HOME:?the row's make_env states no CCL_HOME}"

# clang's __clang_cuda_runtime_wrapper.h includes this unconditionally and no
# cuda-nvcc package ships it — FlagCX never calls cuRAND, so this is a
# compiler-side requirement and the one build-time package this row adds.
# Checked where clang will look for it, since the Makefile passes this same
# directory as -I.
[ -e "$DEVICE_HOME/include/curand_mtgp32_kernel.h" ] \
    || fail "$DEVICE_HOME/include/curand_mtgp32_kernel.h is missing — the device compiler cannot read CUDA's headers"

rm -rf /flagcx
git clone --quiet "$FLAGCX_REPO" /flagcx || fail "cannot clone $FLAGCX_REPO"
cd /flagcx
# The two-step the wheel build uses, and for the same reason: a 40-hex ref has to
# be fetched before it can be checked out, and the checkout is asserted rather
# than assumed — a silent fallback to the default branch would compile a
# well-formed bitcode of the wrong commit. No submodules: the bitcode make reads
# only this tree (bindings/, flagcx/) and third-party/json is not on its include
# path.
if ! git checkout -q "$FLAGCX_REF" 2>/dev/null; then
    git fetch --quiet origin "$FLAGCX_REF" || fail "cannot fetch $FLAGCX_REF"
    git checkout -q FETCH_HEAD
fi
sha="$(printf '%s' "$FLAGCX_REF" | tr '[:upper:]' '[:lower:]')"
if printf '%s' "$sha" | grep -Eq '^[0-9a-f]{40}$'; then
    [ "$(git rev-parse HEAD)" = "$sha" ] \
        || fail "checked out $(git rev-parse HEAD), asked for $sha"
fi
echo ">>> compiling device bitcode at $(git rev-parse --short HEAD)"

# gnu++17 and not the Makefile's own c++17: the device headers under
# nccl_device/ use `typeof`, which is a GNU extension — and only the CCL branch
# reaches them, so this failing would also be the sign that the branch did not
# take. DEVICE_HOME/CCL_HOME come from the export above; the tools are not named
# because the image's PATH already carries them.
make -C bindings/ir/nvidia \
    BUILDDIR=/tmp/bitcode \
    BITCODE_LIB_ARCH="$BITCODE_ARCH" \
    BITCODE_CXX_STD=gnu++17 \
    ADAPTOR_FLAG="$ADAPTOR_FLAG" \
    DEVICE_HOME="$DEVICE_HOME" \
    CCL_HOME="$CCL_HOME"

bc=/tmp/bitcode/lib/libflagcx_device.bc
wrapper=/tmp/bitcode/include/flagcx_device_wrapper.h
# The .bc and this header are the two artifacts the wheel line injects, so both
# are what a builder has to be shown to produce (the Makefile writes the header
# next to the bitcode, out of bindings/flagcx_device_wrapper.h).
for path in "$bc" "$wrapper"; do
    [ -s "$path" ] || fail "$path was not produced"
done

# The size is what says which comm-traits branch the bitcode landed in, and it is
# asserted as a band rather than as a symbol count because it separates the two by
# a factor of seven and does not move with the compiler: measured at 274,820 B for
# DefaultBackend (sm_90 against NCCL 2.25) and 2,021,684 B for CCL (sm_120 against
# NCCL 2.31), the difference being nccl_device's device-side implementation.
size="$(stat -c%s "$bc")"
case "$ADAPTOR_FLAG" in
    *FLAGCX_COMM_TRAITS_CCL*)
        [ "$size" -gt 1000000 ] \
            || fail "$bc is $size bytes — that is DefaultBackend's size, so the CCL branch did not take effect" ;;
    *)
        [ "$size" -lt 1000000 ] && [ "$size" -gt 50000 ] \
            || fail "$bc is $size bytes — outside the range a DefaultBackend bitcode occupies" ;;
esac

llvm-dis "$bc" -o /tmp/bitcode.bc.ll
grep -q 'target triple = "nvptx64-nvidia-cuda"' /tmp/bitcode.bc.ll \
    || fail "$bc does not carry the nvptx64-nvidia-cuda triple — it is not CUDA device bitcode"

echo ">>> ok: $BACKEND, clang $major, $BITCODE_ARCH, $size bytes of bitcode and a $(stat -c%s "$wrapper")-byte wrapper header"
IN_CONTAINER

echo ">>> ok: $IMAGE"
