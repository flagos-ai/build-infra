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
# Verify a FlagCX .deb in the image that built it.
#
# Usage:
#   verify-flagcx-deb.sh --backend metax-maca3.8.1.3 dist/*.deb
#   verify-flagcx-deb.sh --backend nvidia-cuda12.8 --floor-image ubuntu:24.04 dist/*.deb
#
# Options:
#   --backend KEY      backend from backends.yaml; names the base image to
#                      verify in and the vendor whose run flags it needs
#   --floor-image REF  also install into this plain Ubuntu, which must be the
#                      release matching the package's libc6 floor
#   --keep             leave the container behind for inspection
#   -h, --help         this text
#
# Positional arguments are the .deb files to verify (runtime and -dev).
#
# Why this is a container and not a host check: the package has to install with
# apt, and the installed soname has to resolve through the default loader path
# with the vendor symbols bound. A host without the vendor SDK can assert
# neither.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"

OPT_BACKEND=""
OPT_FLOOR_IMAGE=""
KEEP=0
DEBS=()

usage() { sed -n '16,34p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

fail() {
    echo "verify-flagcx-deb.sh: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend)     OPT_BACKEND="${2:?--backend needs a key}"; shift 2 ;;
        --floor-image) OPT_FLOOR_IMAGE="${2:?--floor-image needs an image ref}"; shift 2 ;;
        --keep)        KEEP=1; shift ;;
        -h|--help)     usage; exit 0 ;;
        -*)            echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
        *)             DEBS+=("$1"); shift ;;
    esac
done
[[ -n "$OPT_BACKEND" ]] || { echo "--backend is required" >&2; exit 2; }
[[ ${#DEBS[@]} -gt 0 ]] || { echo "no .deb given" >&2; exit 2; }

cd "$REPO_ROOT"
# Captured into a variable rather than inlined: `set -e` does not see a failure
# inside eval's command substitution, so an inline one would let the script run
# on to the layout checks with every DEB_* empty.
INPUTS="$(python3 packaging/flagcx/deb-config.py --build-inputs "$OPT_BACKEND")"
set -a
eval "$INPUTS"
set +a

# The layout is asserted from the file, before anything is installed: the two
# packages split the same three names between them, and a name on the wrong side
# is a dpkg "trying to overwrite" failure at install time, not a cosmetic one.
RUNTIME_DEB=""
DEV_DEB=""
for deb in "${DEBS[@]}"; do
    pkg="$(dpkg-deb -f "$deb" Package)"
    arch="$(dpkg-deb -f "$deb" Architecture)"
    [[ "$arch" == "$DEB_ARCH" ]] \
        || fail "$deb: Architecture is $arch, expected $DEB_ARCH"
    case "$pkg" in
        "$DEB_PACKAGE")      RUNTIME_DEB="$deb" ;;
        "$DEB_PACKAGE"-dev)  DEV_DEB="$deb" ;;
        *)                   fail "$deb: package $pkg is not $DEB_PACKAGE or $DEB_PACKAGE-dev" ;;
    esac
done
[[ -n "$RUNTIME_DEB" && -n "$DEV_DEB" ]] \
    || fail "need both $DEB_PACKAGE and $DEB_PACKAGE-dev among the given .deb files"

listing="$(dpkg-deb -c "$RUNTIME_DEB")"
VER_LIB="$(awk '$1 ~ /^-/ && $NF ~ /^\.\/usr\/lib\/libflagcx\.so\.[0-9]+(\.[0-9]+)+$/ {print $NF}' <<<"$listing")"
SONAME_LINK="$(awk '$1 ~ /^l/ && $(NF-2) ~ /^\.\/usr\/lib\/libflagcx\.so\.[0-9]+$/ {print $(NF-2), $NF}' <<<"$listing")"
[[ -n "$VER_LIB" ]] || fail "$RUNTIME_DEB: no real libflagcx.so.<version> in /usr/lib"
[[ -n "$SONAME_LINK" ]] || fail "$RUNTIME_DEB: no libflagcx.so.<soname> symlink in /usr/lib"
LIBVER="${VER_LIB##*libflagcx.so.}"
SONAME="${SONAME_LINK%% *}"
SONAME="${SONAME##*libflagcx.so.}"
[[ "$SONAME" == "${LIBVER%%.*}" ]] \
    || fail "$RUNTIME_DEB: soname $SONAME does not match version $LIBVER"
[[ "${SONAME_LINK##* }" == "libflagcx.so.$LIBVER" ]] \
    || fail "$RUNTIME_DEB: soname symlink points at ${SONAME_LINK##* }, not libflagcx.so.$LIBVER"
if awk '$1 ~ /^l/ { p = $(NF-2) } $1 ~ /^-/ { p = $NF } p == "./usr/lib/libflagcx.so" { found = 1 } END { exit !found }' <<<"$listing"; then
    fail "$RUNTIME_DEB: ships the unversioned libflagcx.so, which belongs to -dev"
fi

listing="$(dpkg-deb -c "$DEV_DEB")"
if awk '$1 ~ /^-/ && $NF ~ /^\.\/usr\/lib\/libflagcx\.so\.[0-9]+(\.[0-9]+)*$/ { found = 1 } END { exit !found }' <<<"$listing"; then
    fail "$DEV_DEB: ships the library itself, which belongs to the runtime package"
fi
[[ "$(awk '$1 ~ /^l/ && $(NF-2) == "./usr/lib/libflagcx.so" { print $NF }' <<<"$listing")" == "libflagcx.so.$LIBVER" ]] \
    || fail "$DEV_DEB: /usr/lib/libflagcx.so does not link to libflagcx.so.$LIBVER"
grep -qE '^-.*\./usr/include/flagcx/flagcx\.h$' <<<"$listing" \
    || fail "$DEV_DEB: no /usr/include/flagcx/flagcx.h"
echo ">>> layout: libflagcx.so.$LIBVER, soname libflagcx.so.$SONAME, -dev links and headers present"

# The vendor's device passthrough, from build-config.yml: RTLD_NOW resolves
# against the host's driver, so this container needs the flags a runtime
# container gets. metax is why the chain ends at run.default -- its entry
# carries toolkit_cmd (a wrapper binary CI does not have) and raw, no toolkit.
RUN_FLAGS="$(VENDOR="$DEB_VENDOR" python3 - <<'PY'
import os
import yaml
with open(".github/build-config.yml") as fh:
    run = yaml.safe_load(fh).get("run") or {}
vendor = (run.get("vendors") or {}).get(os.environ["VENDOR"], {})
print(vendor.get("toolkit") or vendor.get("raw") or run.get("default", ""))
PY
)"
# Adding it twice makes docker abort with "network host is specified multiple
# times", and some vendor toolkits already carry it.
if [[ " ${RUN_FLAGS} " != *" --network "* ]]; then
    RUN_FLAGS="${RUN_FLAGS} --network host"
fi

CONTAINER="flagcx-deb-verify-$$"
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

# mode=full  the base image: everything must resolve and load
# mode=floor a plain Ubuntu: only the install is asserted, because the vendor
#            libraries are deliberately not dependencies of the package
verify_in() {
    local image="$1" mode="$2" run_flags="$3"

    echo ">>> $mode: $image $run_flags"
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$CONTAINER" $run_flags "$image" sleep infinity >/dev/null
    docker exec "$CONTAINER" mkdir -p /tmp/debs
    for deb in "${DEBS[@]}"; do
        docker cp "$deb" "$CONTAINER:/tmp/debs/"
    done
    docker cp "$HERE/smoke-load.c" "$CONTAINER:/tmp/smoke-load.c"

    docker exec -i -e MODE="$mode" -e PKG="$DEB_PACKAGE" \
        "$CONTAINER" bash -euo pipefail -s <<'IN_CONTAINER'
export DEBIAN_FRONTEND=noninteractive
# The lists may be absent from the image and the vendor apt sources may need a
# proxy the runner does not have. The install only needs libc6/libstdc++6/
# libgcc-s1, which every Ubuntu ships, so a failed update is a note: if a
# dependency really is unsatisfied the install below still fails.
apt-get update -qq || echo "note: apt-get update failed; local files only" >&2
apt-get install -y --no-install-recommends /tmp/debs/*.deb

# dpkg only runs ldconfig through a trigger, and a stale cache would make the
# dlopen below fail for the wrong reason.
ldconfig

lib="$(dpkg -L "$PKG" | grep -E '^/usr/lib/libflagcx\.so\.[0-9]+(\.[0-9]+)+$')"
soname="$(basename "$(dpkg -L "$PKG" | grep -E '^/usr/lib/libflagcx\.so\.[0-9]+$')")"
[ -n "$lib" ] && [ -n "$soname" ] || { echo "$PKG: nothing installed in /usr/lib" >&2; exit 1; }

if [ "$MODE" = floor ]; then
    echo ">>> floor: $PKG installs here; vendor libraries stay unresolved by design"
    exit 0
fi

if ldd "$lib" | grep -q 'not found'; then
    ldd "$lib" >&2
    echo "$lib: unresolved libraries (the base image's SDK should supply them)" >&2
    exit 1
fi
cc -o /tmp/smoke-load /tmp/smoke-load.c -ldl
/tmp/smoke-load "$soname"
echo ">>> full: $PKG installs, $soname resolves, flagcxGetVersion returns flagcxSuccess"
IN_CONTAINER
}

verify_in "$DEB_BASE_IMAGE" full "$RUN_FLAGS"
if [[ -n "$OPT_FLOOR_IMAGE" ]]; then
    verify_in "$OPT_FLOOR_IMAGE" floor "--network host"
fi

echo ">>> ok: $DEB_PACKAGE ($DEB_ARCH, glibc >= $DEB_GLIBC_FLOOR)"
