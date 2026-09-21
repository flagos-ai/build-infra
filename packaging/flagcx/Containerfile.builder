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
# FlagCX build-toolchain image for one backend. One container, one backend.
#
# The build context is the repository root, not this directory:
#
#   key=nvidia-cuda13.3
#   eval "$(python3 packaging/flagcx/deb-config.py --build-inputs "$key" --channel builder)"
#   docker build \
#       --build-arg "BASE_IMAGE=$DEB_IMAGE_TAG" \
#       --build-arg "DEB_APT=$DEB_APT" \
#       --build-arg "DEB_BUILDER_APT=$DEB_BUILDER_APT" \
#       --build-arg "DEB_ASSERT=$DEB_ASSERT" \
#       --build-arg "LLVM_VERSION=22.1.8" \
#       --build-arg "LLVM_SHA256=df0e1ecf16caf3489a272a5eea4eec9b0d82878f6477fa309504f918a0006384" \
#       -f packaging/flagcx/Containerfile.builder -t "flagos-dev/flagcx-builder:$key" .
#
# packaging/flagcx/build-flagcx-builder.sh is that recipe with the bookkeeping
# around it; it is written out here because it has to be reproducible by hand.
#
# Nothing in here reads backends.yaml.
#
# WHY THIS IMAGE EXISTS AT ALL. BASE_IMAGE is the backend's *runtime* image and
# never a vendor toolchain image, because the wheel build has to run where torch
# is: plugin/torch/_build_config.py imports torch to pick the extension classes
# and the device rpaths, and only /flagos carries torch, setuptools_scm and a
# Python.h for the interpreter that will install the result. Build env ==
# delivery env. This image is therefore the runtime image plus the two things a
# FlagCX build needs that no runtime image ships — the vendor SDK (DEB_APT, the
# same list the .deb line already states) and clang/llvm — and nothing else. It
# is a legitimate image precisely because the runtime image is *insufficient*
# here: the packaging/megatron line rejected a pre-built builder for the
# opposite reason, that its runtime image was already enough.
#
# The vendor SDK rows (hygon, metax, ...) need none of this — their bases carry
# the toolchain — so they build their wheel straight in the runtime image and
# have no `builder` block. Only rows that declare one get an image.

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG DEB_APT
ARG DEB_BUILDER_APT
ARG DEB_ASSERT
ARG LLVM_VERSION
ARG LLVM_SHA256

# Scoped to the LLVM fetch below and never set as image ENV: the proxy is a
# build-time fact of one RUN, and an image that remembers it is an image that
# leaks it.
ARG HTTPS_PROXY=

# git accepts either casing, curl only the lowercase one, and the runners export
# the lowercase pair — so the same fact is declared under both names rather than
# asking the call site for two spellings. The fetch below reads the uppercase
# name, hence its fallback.
ARG http_proxy=
ARG https_proxy=

# Not baked here: which hosts must not be proxied is a fact about the node's
# network, and a second copy in this file silently overrode the node's own
# (measured on the 910c nodes, where the node's value is what took effect and
# the mirror went through the proxy anyway). The call site relays the node's
# value, and that is the only source.
ARG no_proxy=

# DEB_APT is what the adaptor needs on top of the runtime image and is the same
# list Containerfile.deb installs — one fact, stated once, in backends.yaml.
# DEB_BUILDER_APT is this channel's own increment and is build-time-only.
#
# libgflags-dev/libgoogle-glog-dev are here rather than in Containerfile.wheel
# because they are build-only headers that no runtime image ships (torch's
# c10/util/Flags.h and c10/util/Logging.h reach them) and this image is where
# the wheel's build environment now starts; they cost a second only when this
# image is built, instead of on every FLAGCX_REF change.
#
# curl/xz-utils/ca-certificates are unconditional because the LLVM tarball is
# the one thing every builder fetches, and whether a given base happens to ship
# an extractor and a CA bundle is not something this file should depend on.
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ${DEB_APT} ${DEB_BUILDER_APT} \
        libgflags-dev libgoogle-glog-dev \
        curl xz-utils ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The rest of torch's build-time headers. ATen is written against a complete CUDA
# toolkit — ATen/cuda/CUDAContextLight.h includes <cusparse.h> and the wider trees
# reach cublas/cusolver/cufft — while a CUDA *runtime* image ships the libraries
# and not the headers. The wheel build compiles flagcx._C against them, so on the
# nvidia rows this step is the difference between a wheel and a stop at
# cusparse.h (measured: then cublas_v2.h, then cusolverDn.h, then cufft.h).
#
# Installed at the version of the library already in the image rather than at
# apt's candidate, and that is the whole reason this is a loop. apt's candidate
# belongs to the newest CUDA release in the repo — 13.6 while this row's toolkit
# is 13.3 — and satisfying it means upgrading libcublas-13-3 out from under the
# environment the wheel is delivered to. Naming the pair keeps the header and the
# library it describes in step, and reading the version rather than writing it
# down means a base image bump moves both together.
#
# Inert on a row with no CUDA math libraries: the vendor SDK rows build their
# wheel in the runtime image and have no builder at all.
RUN set -eux; \
    apt-get update; \
    for pkg in $(dpkg-query -W -f='${Package}\n' \
            'libcublas-*' 'libcusparse-*' 'libcusolver-*' 'libcufft-*' 2>/dev/null); do \
        case "$pkg" in *-dev) continue ;; esac; \
        dev="$(printf '%s' "$pkg" | sed -E 's/^((lib(cublas|cusparse|cusolver|cufft))-)/\1dev-/')"; \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
            "${dev}=$(dpkg-query -W -f='${Version}' "$pkg")"; \
    done; \
    rm -rf /var/lib/apt/lists/*

# DEB_ASSERT is the list of files that proves the SDK is the one we think it is,
# and it is checked *after* the install above — not before, as
# Containerfile.wheel checks it. That file's early gate is right for the SDK-free
# rows it was written for and is exactly why the nvidia rows could not use the
# wheel channel: it asserts on headers that the runtime image does not carry and
# this image has just installed. Here the assert answers the question the install
# raises, which is whether the packages that landed are the ones the row means.
RUN set -eux; \
    for path in ${DEB_ASSERT}; do \
        test -e "$path" || { echo "assert: $path is missing" >&2; exit 1; }; \
    done

# clang/llvm comes from the official release tarball and not from apt, because
# the floor is 22 and nothing on Ubuntu 24.04 reaches it (the archive stops at
# clang-18/20 and apt.llvm.org at 21). The floor is real and not a preference:
# CUDA 13 removed texture_fetch_functions.h, which clang's CUDA wrapper included
# unconditionally up to 21, and crt/math_functions.h has expected the compiler to
# define _NV_RSQRT_SPECIFIER since CUDA 13.2. Both fixes land in 22. Measured on
# h20 against CUDA 13.3: clang-20 and clang-21 each fail to compile the device
# bitcode, clang-22 compiles it.
#
# Only the five binaries and the resource directory are extracted — 468 MB
# against roughly 10 GB for the whole tarball. clang-22 is statically linked
# against LLVM (there is no libLLVM*.so to carry), so ldd leaves only system
# libraries; lib/clang/<major>/include is the resource directory clang reads its
# own headers from and is not optional.
#
# It lands in /opt/llvm and not in a version-suffixed directory: LLVM_VERSION is
# the only place the version is stated, and a path like /opt/llvm-22 would be a
# second statement of it that cannot be kept in step (Dockerfile ENV has no
# `${VAR%%.*}` to derive it from, so it would have to be a second build arg). The
# version is legible from `clang --version` and from the flagos.llvm.* labels, and
# the interface a consumer uses is the image's PATH, not the directory name.
#
# The tarball is fetched from the filestore first and GitHub second, the same
# order packaging/sglang/build-and-repack.sh uses for its Rust toolchain, and the
# sha256 is checked on whichever route answered: the pin is what makes the
# second route acceptable, and an artifact that does not match it must not reach
# a compiler. The arch token is read from the image rather than passed in — it is
# a fact about where this build runs. An arm64 builder would need its own
# LLVM_SHA256, and the check above is what would say so.
ARG LLVM_FILESTORE=https://resource.flagos.net/repository/flagos-filestore
RUN set -eux; \
    case "$(uname -m)" in \
        x86_64)  llvm_arch=X64 ;; \
        aarch64) llvm_arch=ARM64 ;; \
        *) echo "unsupported machine $(uname -m) for LLVM release tarballs" >&2; exit 1 ;; \
    esac; \
    tarball="LLVM-${LLVM_VERSION}-Linux-${llvm_arch}.tar.xz"; \
    export HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-}}"; \
    curl -fsSL --retry 3 --connect-timeout 15 -o /tmp/llvm.tar.xz \
        "${LLVM_FILESTORE}/llvm/${tarball}" \
        || { echo ">>> ${tarball} is not on the filestore; falling back to github.com"; \
             curl -fsSL --retry 3 --connect-timeout 15 -o /tmp/llvm.tar.xz \
                 "https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VERSION}/${tarball}"; }; \
    echo "${LLVM_SHA256}  /tmp/llvm.tar.xz" | sha256sum -c -; \
    major="${LLVM_VERSION%%.*}"; \
    mkdir -p /opt/llvm; \
    tar -xJf /tmp/llvm.tar.xz -C /opt/llvm --strip-components=1 \
        "LLVM-${LLVM_VERSION}-Linux-${llvm_arch}/bin/clang" \
        "LLVM-${LLVM_VERSION}-Linux-${llvm_arch}/bin/clang-${major}" \
        "LLVM-${LLVM_VERSION}-Linux-${llvm_arch}/bin/llvm-as" \
        "LLVM-${LLVM_VERSION}-Linux-${llvm_arch}/bin/llvm-dis" \
        "LLVM-${LLVM_VERSION}-Linux-${llvm_arch}/bin/opt" \
        "LLVM-${LLVM_VERSION}-Linux-${llvm_arch}/lib/clang/${major}/include"; \
    rm -f /tmp/llvm.tar.xz

# On PATH and not a set of absolute paths handed to make: the tarball's own
# names are clang/opt/llvm-as/llvm-dis, which is exactly what
# bindings/ir/nvidia/Makefile's `CLANG ?= clang` ladder defaults to — so a build
# that runs in this image names no compiler at all, and a build that has to name
# one is a build that is not running here.
ENV PATH=/opt/llvm/bin:$PATH
