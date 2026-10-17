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
#   eval "$(python3 packaging/flagcx/flagcx-config.py --build-inputs "$key" --channel builder)"
#   docker build \
#       --build-arg "BUILDER_APT=$BUILDER_APT" \
#       --build-arg "BUILDER_EXTRA_APT=$BUILDER_EXTRA_APT" \
#       --build-arg "BUILDER_ASSERT=$BUILDER_ASSERT" \
#       --build-arg "TORCH_PIN=$BUILDER_TORCH" \
#       --build-arg "NUMPY_PIN=$BUILDER_NUMPY" \
#       --build-arg "VENDOR_PYPI=$BUILDER_FLAGOS_PYPI" \
#       --build-arg "EXTRA_PYPI=$BUILDER_EXTRA_PYPI" \
#       --build-arg "RUNTIME_PREREQS=$BUILDER_RUNTIME_PREREQS" \
#       --build-arg "PYTHON_VERSION=$BUILDER_PYTHON_VERSION" \
#       --build-arg "NCCL_DEV_DEB=$BUILDER_NCCL_DEV_DEB" \
#       --build-arg "NCCL_DEV_SHA256=$BUILDER_NCCL_DEV_SHA256" \
#       --build-arg "NCCL_LIB_DEB=$BUILDER_NCCL_LIB_DEB" \
#       --build-arg "NCCL_LIB_SHA256=$BUILDER_NCCL_LIB_SHA256" \
#       --build-arg "LLVM_VERSION=f6ded0be" \
#       --build-arg "LLVM_SHA256=3cd1d576a5a8e90454905cab83e6c15cac8e8c711a33d148e4bf8e319fa72d44" \
#       -f packaging/flagcx/Containerfile.builder -t "flagos-dev/flagcx-builder:$key" .
#
# packaging/flagcx/build-flagcx-builder.sh is that recipe with the bookkeeping
# around it; it is written out here because it has to be reproducible by hand.
#
# Nothing in here reads backends.yaml.
#
# WHY THIS IMAGE EXISTS, AND WHY IT IS SELF-CONTAINED ON UBUNTU 22.04.
# The wheel build imports torch at build time (plugin/torch/_build_config.py, for
# the extension classes, the torch suffix and the device rpaths), and the _C.so
# leaves c10d::Work's virtuals to the loader — so the environment the wheel is
# built in has to carry torch + a Python.h for the interpreter that installs the
# result, and nothing else from the runtime layer. It used to be the backend's
# *runtime* image plus the SDK and clang; that made the wheel's glibc floor the
# runtime's (24.04 → glibc 2.38), which aborts on the physical 22.04 hosts the
# bundle installs to. Building here on ubuntu:22.04 instead lowers the floor to
# glibc 2.35 — forward-compatible with 24.04 — without touching the runtime or
# flagtree. The image therefore installs everything the runtime used to provide
# (python 3.12, torch pin) plus the two things only a FlagCX build needs (the
# vendor SDK — nvcc, curand, the CUDA math headers — and clang/llvm).
#
# The vendor SDK rows (hygon, metax, ...) need none of this — their bases carry
# the toolchain — so they build their wheel straight in the runtime image and
# have no `builder` block. Only rows that declare one get an image.

FROM ubuntu:22.04

ARG BUILDER_APT
ARG BUILDER_EXTRA_APT
ARG BUILDER_ASSERT
ARG TORCH_PIN
ARG NUMPY_PIN
ARG VENDOR_PYPI
ARG EXTRA_PYPI
ARG PYTHON_VERSION=3.12
ARG RUNTIME_PREREQS
ARG LLVM_VERSION
ARG LLVM_SHA256

# Scoped to the fetch steps below and never set as image ENV: the proxy is a
# build-time fact of a RUN, and an image that remembers it is an image that
# leaks it.
ARG HTTPS_PROXY=

# git accepts either casing, curl only the lowercase one, and the runners export
# the lowercase pair — so the same fact is declared under both names rather than
# asking the call site for two spellings. The fetches below read the uppercase
# name, hence its fallback.
ARG http_proxy=
ARG https_proxy=

# Not baked here: which hosts must not be proxied is a fact about the node's
# network, and a second copy in this file silently overrode the node's own
# (measured on the 910c nodes). The call site relays the node's value, and that
# is the only source.
ARG no_proxy=

# System build deps + python 3.12 (deadsnakes), the way packaging/flagtree/
# nvidia-cuda does it.
#
# THE DEADSNAKES PPA IS WIRED UP BY HAND, NOT WITH add-apt-repository. That
# command resolves the PPA through Launchpad's REST API, and the CI runner's
# proxy answers the CONNECT to api.launchpad.net with 500. The two hosts actually
# needed — the key server and the package archive — are both reachable, so the
# key is fetched and the source line written directly. The codename is jammy
# because this image is ubuntu:22.04 by design.
#
# python3.12 is hardcoded rather than templated from PYTHON_VERSION: both rows
# this file currently builds (nvidia-cuda12.8, nvidia-cuda13.3) are python 3.12
# in configs.yaml, and a bump means editing this line — the same trade
# packaging/flagtree/nvidia-cuda already made. PYTHON_VERSION is still asserted
# by the probe below, so a row that moved would fail loudly rather than build
# with the wrong interpreter.
#
# libgflags-dev/libgoogle-glog-dev are here rather than in Containerfile.wheel
# because they are build-only headers (torch's c10/util/Flags.h and Logging.h
# reach them) and this image is where the wheel's build environment starts.
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates gnupg curl wget git \
        build-essential gcc g++; \
    curl -fsSL \
         "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF23C5A6CF475977595C89F51BA6932366A755776" \
         | gpg --dearmor -o /etc/apt/trusted.gpg.d/deadsnakes.gpg; \
    echo "deb https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu jammy main" \
         > /etc/apt/sources.list.d/deadsnakes.list; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3.12-dev \
        libgflags-dev libgoogle-glog-dev; \
    rm -rf /var/lib/apt/lists/*

# The vendor SDK, from the CUDA repo's ubuntu2204 suite. BUILDER_APT is the
# row's nvcc (the .deb line's `apt` list minus the libnccl* entries, which the
# build script filters out — those come from dpkg-deb -x below). BUILDER_EXTRA_APT
# is this channel's own increment, declared per-row in backends.yaml `builder`:
# curand's mtgp32 header (clang's CUDA wrapper force-includes it, no cuda-nvcc
# package ships it, FlagCX never calls cuRAND), cccl (cub/thrust/libcudacxx,
# reached by NCCL's nccl_device.h on the CCL branch), and the four CUDA math
# -dev packages torch's ATen headers reach.
#
# The math -dev packages are installed UNVERSIONED, deviating from the runtime-
# based builder that installed them "at the version already in the image". That
# trick existed to avoid apt upgrading a preinstalled runtime lib out from under
# the delivery environment; a fresh ubuntu:22.04 has none preinstalled, and the
# wheel's .so links no math lib (its NEEDED are nccl/cudart/cuda/libstdc++), so
# the headers are consumed only for torch's transitive includes. The package
# name pins the CUDA track; a patch drift within it is invisible to the artifact.
#
# The repo is wired by installing cuda-keyring, which drops the sources.list and
# the pin file in one .deb.
RUN set -eux; \
    curl -fsSL --retry 3 --connect-timeout 15 \
        -o /tmp/cuda-keyring.deb \
        "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb"; \
    dpkg -i /tmp/cuda-keyring.deb; \
    rm -f /tmp/cuda-keyring.deb; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ${BUILDER_APT} ${BUILDER_EXTRA_APT}; \
    rm -rf /var/lib/apt/lists/*

# NCCL, exact-pinned, from the ubuntu2404 repo by dpkg-deb -x and NOT by apt.
# The exact pins exist only in the 2404 suite (the 2204 one carries 2.32.3), and
# that suite's control block demands libc6 >= 2.38 — which dpkg would refuse on
# this 22.04 image. Extracting the .debs bypasses the floor, but the 2404-built
# libnccl.so itself still LINKS GLIBC_2.38: it lands here only to *link against*
# (the wheel records NEEDED libnccl.so.2 and undefined nccl* symbols, never the
# dependency's own glibc needs), so the builder never runs it. nccl.h is what
# nvidia.mk reads for the comm-traits branch; the unversioned libnccl.so symlink
# (in -dev) is what -lnccl resolves. Both .debs are sha256-pinned like the LLVM
# tarball, because a .deb fetched over this network must not reach a linker
# without being the bytes the pin names. The sha256 values travel as build args
# from flagcx-config.py (next to the derivation that names the .debs), so the
# check is `sha256sum -c` against a real string and never a silent skip.
#
# The dev .deb is extracted LAST: it carries the libnccl.so -> libnccl.so.2
# symlink, and libnccl2 (first) is the one that provides the file it points at.
ARG NCCL_REPO=https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64
ARG NCCL_DEV_DEB
ARG NCCL_DEV_SHA256
ARG NCCL_LIB_DEB
ARG NCCL_LIB_SHA256
RUN set -eux; \
    export HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-}}"; \
    curl -fsSL --retry 5 --connect-timeout 15 -o /tmp/nccl-lib.deb \
        "${NCCL_REPO}/${NCCL_LIB_DEB}"; \
    echo "${NCCL_LIB_SHA256}  /tmp/nccl-lib.deb" | sha256sum -c -; \
    curl -fsSL --retry 5 --connect-timeout 15 -o /tmp/nccl-dev.deb \
        "${NCCL_REPO}/${NCCL_DEV_DEB}"; \
    echo "${NCCL_DEV_SHA256}  /tmp/nccl-dev.deb" | sha256sum -c -; \
    dpkg-deb -x /tmp/nccl-lib.deb /; \
    dpkg-deb -x /tmp/nccl-dev.deb /; \
    rm -f /tmp/nccl-dev.deb /tmp/nccl-lib.deb; \
    test -e /usr/include/nccl.h; \
    test -L /usr/lib/x86_64-linux-gnu/libnccl.so; \
    test -e /usr/lib/x86_64-linux-gnu/libnccl.so.2

# BUILDER_ASSERT is the list of files that proves the SDK is the one we think it
# is, checked after the installs above (the nvidia rows could not use the wheel
# channel's early gate: it asserts on headers only this image installs). Here
# the assert answers the question the install raises, which is whether the
# packages that landed are the ones the row means.
RUN set -eux; \
    for path in ${BUILDER_ASSERT}; do \
        test -e "$path" || { echo "assert: $path is missing" >&2; exit 1; }; \
    done

# The interpreter and torch, the two things the runtime image used to provide.
# /flagos is the same path the runtime image and Containerfile.wheel use, so the
# wheel build's probe and its `pip wheel` command run unchanged.
#
# numpy rides with the prereqs because it is in the row's deps (the delivery
# image carries it) and the wheel build's `import torch` warns when it is absent
# — one warning per build is enough of a reason to install it here, and the pin
# comes from the same `deps` list as torch so the two cannot disagree.
#
# Two indexes the way runtime/Containerfile splits them: RUNTIME_PREREQS come
# from the general mirror (pybind11/ninja/PyYAML/setuptools-scm are not on the
# vendor index), and torch comes from the vendor index LAST so its own deps
# (triton, sympy, ...) resolve on the mirror while +cu128/+cu130 resolves on the
# vendor. wheel + packaging ride along because setuptools_scm and the build
# import them (Containerfile.wheel's probe asserts both).
#
# PYTHON_VERSION is the matrix row's, relayed through flagcx-config.py: it is
# what the venv probe asserts the interpreter against, and a row that moved to
# another Python would fail there — but the python3.12 packages themselves are
# hardcoded in the system-deps step above, which a moved row cannot change. Both
# NVIDIA rows are 3.12 today, and the mismatch a future bump would trip is
# named in that step's comment.
ENV VIRTUAL_ENV=/flagos \
    PATH="/flagos/bin:${PATH}"
RUN set -eux; \
    python3.12 -m ensurepip --upgrade; \
    python3.12 -m pip install --no-cache-dir --upgrade pip wheel setuptools; \
    python3.12 -m venv /flagos; \
    /flagos/bin/pip install --no-cache-dir --upgrade pip; \
    /flagos/bin/pip install --no-cache-dir --index-url "${EXTRA_PYPI}" \
        ${RUNTIME_PREREQS} ${NUMPY_PIN} wheel packaging; \
    for i in 1 2 3; do \
        PIP_INDEX_URL="${EXTRA_PYPI}" \
        PIP_EXTRA_INDEX_URL="${VENDOR_PYPI}" \
        PIP_TRUSTED_HOST=resource.flagos.net \
        /flagos/bin/pip install --no-cache-dir --pre "${TORCH_PIN}" && break; \
        echo "torch install attempt $i failed, retrying in 10s..."; sleep 10; \
    done

# The probe the wheel build stands in for: the same imports Containerfile.wheel
# asserts, plus the torch version that distinguishes one NVIDIA row from the
# other. TORCH_DEVICE_BACKEND_AUTOLOAD=0 is what setup.py sets for itself before
# importing anything. The interpreter reaches python on stdin rather than a
# here-doc body, for the classic builder (see Containerfile.wheel).
RUN set -eu; \
    printf '%s\n' \
      'import importlib' \
      'import importlib.metadata' \
      'import os' \
      'import sys' \
      'import sysconfig' \
      '' \
      'for name in ("torch", "setuptools", "setuptools_scm", "wheel", "packaging",' \
      '             "torch.utils.cpp_extension"):' \
      '    importlib.import_module(name)' \
      '' \
      'header = os.path.join(sysconfig.get_paths()["include"], "Python.h")' \
      'assert os.path.exists(header), "no Python.h under %s" % header' \
      '' \
      'want_minor = int(os.environ["PYTHON_VERSION"].split(".", 1)[1])' \
      'assert sys.version_info[:2] == (3, want_minor), "the venv is %s, the row says %s" % (sys.version_info[:2], os.environ["PYTHON_VERSION"])' \
      '' \
      'import torch' \
      'want_torch = os.environ["TORCH_PIN"].split("==", 1)[1]' \
      'assert torch.__version__ == want_torch, "torch %s, the row pins %s" % (torch.__version__, want_torch)' \
      'print(">>> build env: %s, cp3%d, torch %s, setuptools_scm %s"' \
      '      % (sys.executable, want_minor, torch.__version__,' \
      '         importlib.metadata.version("setuptools_scm")))' \
    | TORCH_DEVICE_BACKEND_AUTOLOAD=0 PYTHON_VERSION="${PYTHON_VERSION}" \
      TORCH_PIN="${TORCH_PIN}" /flagos/bin/python -

# clang/llvm comes from a snapshot tarball and not from apt, because the floor
# is 22 and nothing on Ubuntu 24.04 reaches it (the archive stops at clang-18/20
# and apt.llvm.org at 21). The floor is real and not a preference: CUDA 13
# removed texture_fetch_functions.h, which clang's CUDA wrapper included
# unconditionally up to 21, and crt/math_functions.h has expected the compiler
# to define _NV_RSQRT_SPECIFIER since CUDA 13.2. Both fixes land in 22.
#
# The exact 22.0.0git snapshot f6ded0be (not an official release) is what the
# reader is: flagtree embeds it, and the flagcx wheel's .bc must parse in that
# reader's parseIRFile. Bitcode written by 22.1.8 fails with "Unknown attribute
# kind (105)". The tarball is the flagtree `mlir` wheel's llvm_artifact
# bin/{clang,llvm-as,llvm-dis,opt} plus its resource dir, with the
# _NV_RSQRT_SPECIFIER block back-ported, REBUILT ON UBUNTU 22.04 so the compiler
# itself links nothing past glibc 2.34 (the 24.04-built original linked
# GLIBC_2.38 and could not run here). Its clang --version names the f6ded0be
# revision, which verify-flagcx-builder.sh asserts.
#
# Only the five binaries and the resource directory are extracted. clang is
# statically linked against LLVM (there is no libLLVM*.so to carry), so ldd
# leaves only system libraries; lib/clang/<major>/include is the resource
# directory clang reads its own headers from and is not optional.
#
# It lands in /opt/llvm and not in a version-suffixed directory for the reason
# stated in the previous incarnation of this file: LLVM_VERSION is the only
# place the version is stated, and the interface a consumer uses is PATH.
#
# The tarball is fetched from the filestore (no second route). The sha256 is
# checked: the pin is what makes the fetch acceptable. The arch token is read
# from the image — an arm64 builder would need its own tarball and LLVM_SHA256.
ARG LLVM_FILESTORE=https://resource.flagos.net/repository/flagos-filestore
RUN set -eux; \
    case "$(uname -m)" in \
        x86_64)  llvm_arch=x64 ;; \
        aarch64) llvm_arch=arm64 ;; \
        *) echo "unsupported machine $(uname -m) for the LLVM snapshot tarball" >&2; exit 1 ;; \
    esac; \
    tarball="llvm-${LLVM_VERSION}-clang-ubuntu-${llvm_arch}-2204.tar.gz"; \
    export HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-}}"; \
    curl -fsSL --retry 3 --connect-timeout 15 -o /tmp/llvm.tar.gz \
        "${LLVM_FILESTORE}/llvm/${tarball}"; \
    echo "${LLVM_SHA256}  /tmp/llvm.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/llvm; \
    tar -xzf /tmp/llvm.tar.gz -C /opt/llvm --strip-components=1 \
        "clangpkg/bin/clang" \
        "clangpkg/bin/clang-22" \
        "clangpkg/bin/clang++" \
        "clangpkg/bin/llvm-as" \
        "clangpkg/bin/llvm-dis" \
        "clangpkg/bin/opt" \
        "clangpkg/lib/clang/22/include"; \
    rm -f /tmp/llvm.tar.gz

# On PATH and not a set of absolute paths handed to make: the tarball's own
# names are clang/opt/llvm-as/llvm-dis, which is exactly what
# bindings/ir/nvidia/Makefile's `CLANG ?= clang` ladder defaults to. /flagos/bin
# stays ahead of the system python so `python` is the venv's, while /opt/llvm
# is ahead of both so the compiler the build names is the pinned one.
ENV PATH=/opt/llvm/bin:/flagos/bin:$PATH
