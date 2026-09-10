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
# Turn the freshly installed libflagcx.so into a normal versioned shared object.
#
# Usage: patch-soname.sh <installed libflagcx.so> <upstream version> <dev tree>
#
# The FlagCX `install:` target is a flat `cp` of a build-tree artifact, so three
# things have to be fixed up before dpkg sees it:
#
#   1. no version in the leaf name      -> libflagcx.so.0.14.0
#   2. no SONAME at all                 -> DT_SONAME libflagcx.so.0
#   3. an rpath baked at link time      -> stripped
#
# (3) is not optional: Makefile:343 passes -Wl,-rpath for LIBDIR, CCL_LIB,
# HOST_CCL_LIB and UCX_LIB, which would ship absolute build-host paths in
# DT_RUNPATH — including $(BUILDDIR)/lib, a directory that does not exist on any
# machine the package is installed on. The dynamic linker needs no rpath here:
# the vendor libraries are found through the site's own ld.so configuration.

set -euo pipefail

SO="${1:?usage: patch-soname.sh <libflagcx.so> <version> <dev-tree>}"
VER="${2:?usage: patch-soname.sh <libflagcx.so> <version> <dev-tree>}"
DEV_TREE="${3:?usage: patch-soname.sh <libflagcx.so> <version> <dev-tree>}"

[[ -f "$SO" ]] || { echo "patch-soname.sh: no such file: $SO" >&2; exit 1; }
[[ "$(head -c 4 "$SO" | od -An -tx1 | tr -d ' \n')" == 7f454c46 ]] \
    || { echo "patch-soname.sh: $SO is not an ELF object" >&2; exit 1; }

# Derived, not hardcoded: `libflagcx.so.0` is right for 0.x, but the day
# upstream ships 1.0.0 the soname has to move with it or every consumer of the
# package links against a version that no longer exists.
SOVERSION="${VER%%.*}"
SONAME="libflagcx.so.$SOVERSION"

DIR="$(dirname "$SO")"
VER_SO="$DIR/libflagcx.so.$VER"

mv "$SO" "$VER_SO"
patchelf --set-soname "$SONAME" "$VER_SO"
patchelf --remove-rpath "$VER_SO"

# The runtime package ships the soname link (what a consumer's DT_NEEDED
# resolves to) and the -dev package ships the unversioned link (what `-lflagcx`
# resolves to). Same target, different packages, so the split is by purpose and
# not by anything the linker can infer.
ln -sf "libflagcx.so.$VER" "$DIR/$SONAME"
mkdir -p "$DEV_TREE/usr/lib"
ln -sf "libflagcx.so.$VER" "$DEV_TREE/usr/lib/libflagcx.so"

# A soname that is not what patchelf reported would silently break every
# downstream link, and nothing later in the dh sequence re-reads it.
reported="$(patchelf --print-soname "$VER_SO")"
[[ "$reported" == "$SONAME" ]] \
    || { echo "patch-soname.sh: SONAME is $reported, expected $SONAME" >&2; exit 1; }
if patchelf --print-rpath "$VER_SO" | grep -q .; then
    echo "patch-soname.sh: rpath survived on $VER_SO" >&2
    exit 1
fi
