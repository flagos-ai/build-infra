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
# The half of the wheel build that runs with the row's devices visible.
#
# Containerfile.wheel prepares an image: the SDK assert, the two build-only
# headers, the interpreter probe, the clone at the asked-for ref. This file is
# what runs next in a container made from that image, and it is the wheel itself.
#
# It is not a RUN in that Containerfile, and cannot be: `docker build` gives its
# RUN steps no devices. plugin/torch/_build_config.py imports torch to pick the
# extension classes, and torch's vendor bridge aborts at import when no device is
# visible (sunrise's torch_ptpu, tsingmicro's torch_txda) — so on those rows the
# build died before it compiled anything. build-flagcx-wheel.sh therefore starts
# this container with the row's run.vendors flags from build-config.yml, the same
# pairs packaging/flagcx/verify/verify-flagcx-wheel.sh verifies in: the build
# environment is the delivery environment, and the device it needs is the one the
# verify script passes.
#
# Every input arrives as environment set by that exec (-e NAME=value, values from
# flagcx-config.py --build-inputs), so nothing here is interpolated into a shell
# string on the host. /output is a bind mount: it is where the artifacts land for
# the host to collect, and where the two provenance files beside the wheel go.
#
# cwd is /flagcx, the prepared clone (Containerfile.wheel's WORKDIR).

set -eux

# DTK ships its environment in /etc/profile.d, which a login shell reads and this
# one does not (measured on hygon: `import torch` fails on libgalaxyhip.so.5 with
# an empty LD_LIBRARY_PATH). Sourced before the exports below so that the
# CUDA_PATH handed in wins over anything the file sets.
if [ -f /etc/profile.d/vendor.sh ]; then . /etc/profile.d/vendor.sh; fi

# setuptools_scm's default is --abbrev=40 (git.py DEFAULT_DESCRIBE), which puts a
# full SHA in the wheel name and in every pin written from it. Recorded below and
# in the describe_command just under it, which have to agree: the host checks the
# name's node segment against this record.
FLAGCX_SCM_ABBREV="${FLAGCX_SCM_ABBREV:-7}"

# The commit and the tag landscape are written out for the host to check: the
# wheel's own name is the only thing that carries the version, and it is written
# by a version scheme that reads this clone. The local part's node segment is the
# only place the wheel states its own provenance, so a ref that silently resolved
# to another commit would otherwise produce a well-formed wheel of the wrong
# thing. Written before the build, which only adds untracked files.
mkdir -p /output
git rev-parse HEAD > /output/commit.txt
git describe --tags --always --abbrev="${FLAGCX_SCM_ABBREV}" > /output/scm-describe.txt

# A runner that exports SETUPTOOLS_SCM_PRETEND_VERSION (vllm-plugin-wheel.yml
# does, for its own wheel) would otherwise override the tag-derived version here
# and produce a wheel whose name has nothing to do with the commit.
unset SETUPTOOLS_SCM_PRETEND_VERSION SETUPTOOLS_SCM_PRETEND_VERSION_FOR_FLAGCX

# COMPILE_KERNEL=1 follows the bitcode arg rather than being its own input: a row
# cannot publish a `.bc` its `.so` cannot service.
#
# The two FLAGCX_BITCODE_* variables are the same switch read by setup.py, which
# builds the device bitcode and carries it into the wheel along with the headers
# a consumer compiles against. Building it there rather than here is what makes
# the wheel self-consistent: the archive and its RECORD are written once, by the
# one process that knows everything that went into them.
#
# NVCC_PREPEND_FLAGS — the device units need C++20 (third-party/json) and nvcc's
# default is below it — is PREPEND and not CXXFLAGS so the host objects keep the
# standard the Makefile chose; that flag never reaches nvcc's front end.
if [ -n "${WHEEL_BITCODE_ARCH}" ]; then
    export COMPILE_KERNEL=1 NVCC_PREPEND_FLAGS="-std=c++20" \
           FLAGCX_BITCODE_ARCH="${WHEEL_BITCODE_ARCH}" \
           FLAGCX_BITCODE_ADAPTOR_FLAGS="${WHEEL_BITCODE_ADAPTOR_FLAG}"
fi

# FLAGCX_ADAPTOR is given rather than detected: the adaptor is a property of the
# registry row, not of the container's PATH, and _build_config.py's fallback also
# scans USE_* variables that this build does not set.
#
# CUDA_PATH is read by the vendored torch, not by make: _build_config.py:284
# takes it (or CUDA_HOME) and otherwise falls back to /usr/local/cuda, which
# neither DTK nor MACA has. An empty value is not inert — the metax torch calls
# set_wcuda_gnu_path() at import (cpp_extension.py:287) to set CXX from
# $CUDA_PATH/bin/gnu, and only warns when it finds none. hygon's value is its
# DEVICE_HOME (the two roots coincide); MACA's is its own field, because its
# device root and its cu-bridge toolchain are different directories.
#
# --no-build-isolation: pyproject.toml requires torch, so isolation would go to
# an index for it. --no-deps: setup.py declares no install_requires and
# pyproject.toml no dependencies, so this turns "nothing was pulled in" into a
# failure instead of a silent extra dependency inside the wheel.
export SETUPTOOLS_SCM_OVERRIDES_FOR_FLAGCX='{scm.git.describe_command="git describe --dirty --tags --long --abbrev='"${FLAGCX_SCM_ABBREV}"' --match *[0-9]*"}' \
       FLAGCX_ADAPTOR="${WHEEL_ADAPTOR}" \
       FLAGCX_TORCH_BACKEND="${WHEEL_TORCH_BACKEND}" \
       FLAGCX_VERSION_SUFFIX="${WHEEL_VERSION_SUFFIX}" \
       CUDA_PATH="${WHEEL_CUDA_PATH}" \
       ${WHEEL_MAKE_ENV}
/flagos/bin/python -m pip wheel --no-build-isolation --no-deps --no-cache-dir -w /output .
ls -la /output

# Exactly one wheel, asserted by the glob — and by its existence, since an
# unmatched pattern stays literal in /bin/sh and would count as one. A second
# wheel means something else in the tree is installable, and the pin cannot tell
# them apart: it names a version, not a file.
set -- /output/flagcx-*.whl
test "$#" -eq 1 -a -e "$1" \
    || { ls -1 /output >&2; echo "assert: $# wheels in /output, expected exactly 1" >&2; exit 1; }
ls -1 /output/flagcx-*.whl

# The glibc floor, asserted on the artifact and not on the image that built it.
# This image is ubuntu:22.04 on purpose (see Containerfile.builder): a wheel
# built here links at most glibc 2.35, which is what lets the bundle install it
# on physical 22.04 hosts. The 24.04-built wheel this replaces linked GLIBC_2.38
# and its __isoc23_* family — all tagged 2.38 — and aborted on import there. A
# future build that drifts back (a base bumped under this file, or a header
# picked up from a wrong SDK) fails here, at the wheel, rather than on a user's
# host. The forbidden list and the max-version check mirror packaging/flagtree's
# iluvatar gate; libstdc++ is covered by forbidding GLIBCXX_3.4.31/32, which is
# all a 22.04 toolchain could not have produced.
/flagos/bin/python - "$1" <<'PY'
import os
import re
import subprocess
import sys
import tempfile
import zipfile

wheel = sys.argv[1]
tmp = tempfile.mkdtemp()
zipfile.ZipFile(wheel).extractall(tmp)

so_files = []
for pat in ("flagcx/lib/libflagcx.so", "flagcx/_C*.so"):
    import glob
    so_files += glob.glob(os.path.join(tmp, pat))
so_files.sort()
if not so_files:
    print("FAIL: the wheel carries no libflagcx.so and no _C*.so", file=sys.stderr)
    sys.exit(1)

forbidden = ["GLIBC_2.38", "GLIBCXX_3.4.31", "GLIBCXX_3.4.32", "__isoc23_"]

for so in so_files:
    syms = subprocess.check_output(["objdump", "-T", so], text=True)
    hits = [f for f in forbidden if f in syms]
    if hits:
        print("FAIL: 22.04-incompatible symbols in %s: %s"
              % (os.path.basename(so), hits), file=sys.stderr)
        sys.exit(1)
    versions = re.findall(r"GLIBC_[0-9.]+", syms)
    if versions:
        maxv = max(versions, key=lambda v: [int(x) for x in v[6:].split(".")])
    else:
        maxv = "GLIBC_<none>"
    want = [2, 35]
    if versions and [int(x) for x in maxv[6:].split(".")] > want:
        print("FAIL: %s links %s, above the 2.35 this 22.04 build guarantees"
              % (os.path.basename(so), maxv), file=sys.stderr)
        sys.exit(1)
    print("OK: %s is 22.04-clean (max %s, no forbidden symbols)"
          % (os.path.basename(so), maxv))
PY
