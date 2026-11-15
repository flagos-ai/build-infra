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
# Runs inside the container verify-flagcx-wheel.sh started.
#
# Environment: MODE, WANT_VERSION, WHEEL, INDEX, PIN, EXPECT_SHA, BITCODE_ARCH.

set -euo pipefail

PY=/flagos/bin/python

# A vendor image can print on stdout while a package imports, so a value read
# back from $PY names itself and is matched by that name.
py_value() {
    local marker="$1" code="$2" out n
    out="$("$PY" -c "$code")"
    n="$(printf '%s\n' "$out" | grep -c "^${marker}=" || true)"
    [ "$n" -eq 1 ] \
        || { echo "$PY printed $n $marker lines, not one: $out" >&2; exit 1; }
    printf '%s\n' "$out" | sed -n "s/^${marker}=//p"
}

# A preinstalled flagcx would answer every assertion below. Metadata, not
# importability: pip keys its own install on metadata.
if (cd /tmp && "$PY" -c 'import importlib.metadata as m; m.version("flagcx")') >/dev/null 2>&1; then
    echo ">>> the image already carries a flagcx — uninstalling it"
    "$PY" -m pip uninstall -y flagcx
fi

if [ "$MODE" = index ]; then
    : "${INDEX:?}" "${PIN:?}" "${EXPECT_SHA:?}"
    rm -rf /tmp/dl
    mkdir -p /tmp/dl
    "$PY" -m pip download --no-deps --no-cache-dir --dest /tmp/dl --index-url "$INDEX" "$PIN"
    dl="$(ls -1 /tmp/dl)"
    [ "$(printf '%s\n' "$dl" | wc -l)" -eq 1 ] \
        || { echo "$INDEX: the pin resolved to $dl" >&2; exit 1; }
    # A space in the name is what a registry that decodes the local part's `+`
    # produces, and no hash shows it.
    case "$dl" in
        *" "*) echo "$INDEX: serves '$dl', a name with a space in it — the + of the local part was decoded" >&2; exit 1 ;;
    esac
    case "$dl" in
        "flagcx-$WANT_VERSION-"*.whl) ;;
        *) echo "$INDEX: serves $dl, this build is flagcx-$WANT_VERSION" >&2; exit 1 ;;
    esac
    # Says the index holds this artifact and not a rebuild of the same name.
    got="$(sha256sum "/tmp/dl/$dl" | awk '{print $1}')"
    [ "$got" = "$EXPECT_SHA" ] \
        || { echo "$INDEX: serves $got, this build is $EXPECT_SHA" >&2; exit 1; }
    "$PY" -m pip install --no-deps --no-cache-dir --index-url "$INDEX" "$PIN"
    SOURCE="$INDEX"
else
    # --no-index: nothing may come from a network, so a pass says the wheel is
    # complete rather than that an index filled a gap.
    "$PY" -m pip install --no-deps --no-index --no-cache-dir "$WHEEL"
    SOURCE="the wheel"
fi

installed="$(py_value FLAGCX_VERSION 'import importlib.metadata as m; print("FLAGCX_VERSION=" + m.version("flagcx"))')"
[ "$installed" = "$WANT_VERSION" ] \
    || { echo "flagcx: $SOURCE installs $installed, this build is $WANT_VERSION" >&2; exit 1; }

site="$(py_value FLAGCX_SITE 'import os, flagcx; print("FLAGCX_SITE=" + os.path.dirname(os.path.dirname(flagcx.__file__)))')"
set -- $site/flagcx-*.dist-info
[ "$#" -eq 1 ] && [ -d "$1" ] \
    || { echo "flagcx: $# dist-info directories in $site, expected the one this install wrote" >&2; exit 1; }
metadata="$1/METADATA"

# --no-deps is why a declared dependency is invisible to every check here.
if grep -q '^Requires-Dist:' "$metadata"; then
    grep '^Requires-Dist:' "$metadata" >&2
    echo "$metadata: the wheel declares a dependency, and --no-deps is the only reason nothing pulled it in" >&2
    exit 1
fi

lib="$site/flagcx/lib/libflagcx.so"
[ -f "$lib" ] \
    || { echo "flagcx: $lib is not on disk — the wheel's own payload did not survive the install" >&2; exit 1; }

# No import reaches the device bitcode: a wheel that dropped it installs and
# imports exactly like one that has it.
if [ -n "${BITCODE_ARCH:-}" ]; then
    bc="$site/flagcx/lib/libflagcx_device.bc"
    hdr="$site/flagcx/include/flagcx_device_wrapper.h"
    for f in "$bc" "$hdr"; do
        [ -s "$f" ] \
            || { echo "flagcx: $f is missing or empty — the $BITCODE_ARCH device bitcode did not survive the install" >&2; exit 1; }
    done
    [ "$(head -c 2 "$bc")" = "BC" ] \
        || { echo "flagcx: $bc does not start with the LLVM bitcode magic" >&2; exit 1; }
    echo ">>> device bitcode: $bc ($(stat -c%s "$bc") bytes, $BITCODE_ARCH) and $(basename "$hdr")"
fi

# ldd is a bash script and the import below is not, and naming the unresolved
# library here beats an ImportError that names nothing. torch's library
# directory is where libc10/libtorch live.
unset BASH_ENV
torch_lib="$(py_value FLAGCX_TORCH_LIB 'import os, torch; print("FLAGCX_TORCH_LIB=" + os.path.join(os.path.dirname(torch.__file__), "lib"))')"
for candidate in "$lib" $(find "$site/flagcx" -name '_C*.so'); do
    if LD_LIBRARY_PATH="$torch_lib:${LD_LIBRARY_PATH:-}" ldd "$candidate" | grep -q 'not found'; then
        LD_LIBRARY_PATH="$torch_lib:${LD_LIBRARY_PATH:-}" ldd "$candidate" >&2
        echo "$candidate: unresolved libraries (neither this image's SDK nor the interpreter's own runtime supplies them)" >&2
        exit 1
    fi
done

"$PY" -c 'import flagcx, flagcx.api' >/dev/null
echo ">>> $MODE: flagcx $installed imports, $lib and its dependencies resolve, no Requires-Dist"
