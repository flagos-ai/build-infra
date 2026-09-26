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
# Verify a FlagCX wheel as a file, and as the vendor index serves it.
#
# Usage:
#   verify-flagcx-wheel.sh --wheel dist/*.whl
#   verify-flagcx-wheel.sh --index-url "$matrix.flagos_pypi" --pin "$WHEEL_PIN" \
#       --expect-sha256 "$WHEEL_SHA256"
#
# Options:
#   --wheel            install the given wheels by file path, with no index and
#                      no network: the artifact on its own
#   --index-url URL    install by pin from this index instead
#   --pin PIN          `flagcx==<public>+<local>`, the version the index holds
#   --expect-sha256 H  sha256 of the wheel that was built, the hash alone
#   --backend KEY      backend from backends.yaml; read off the artifact when
#                      this is absent
#   --keep             leave the container behind for inspection
#   -h, --help         this text
#
# Positional arguments are the wheels to verify, in --wheel mode only: the
# read-back installs by pin and touches no file.
#
# Why this is a container and not a host check: the wheel has to install into
# the interpreter that will import it — /flagos, which only the runtime image
# has — and the extension it installs has to load against the vendor libraries
# that image carries. A host without the vendor SDK can assert neither.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"

OPT_INDEX_URL=""
OPT_PIN=""
OPT_EXPECT_SHA256=""
OPT_BACKEND=""
LOCAL_MODE=0
KEEP=0
WHEELS=()

usage() { sed -n '16,35p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

fail() {
    echo "verify-flagcx-wheel.sh: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wheel)          LOCAL_MODE=1; shift ;;
        --index-url)      OPT_INDEX_URL="${2:?--index-url needs a URL}"; shift 2 ;;
        --pin)            OPT_PIN="${2:?--pin needs a value}"; shift 2 ;;
        --expect-sha256)  OPT_EXPECT_SHA256="${2:?--expect-sha256 needs a hash}"; shift 2 ;;
        --backend)        OPT_BACKEND="${2:?--backend needs a key}"; shift 2 ;;
        --keep)           KEEP=1; shift ;;
        -h|--help)        usage; exit 0 ;;
        -*)               echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
        *)                WHEELS+=("$1"); shift ;;
    esac
done

if (( LOCAL_MODE )); then
    [[ -z "$OPT_INDEX_URL$OPT_PIN$OPT_EXPECT_SHA256" ]] \
        || fail "--wheel is the file mode; --index-url/--pin/--expect-sha256 are the read-back's"
    [[ ${#WHEELS[@]} -gt 0 ]] || { echo "no wheel given" >&2; exit 2; }
else
    [[ -n "$OPT_INDEX_URL" && -n "$OPT_PIN" && -n "$OPT_EXPECT_SHA256" ]] \
        || fail "give --wheel with the wheels, or --index-url with --pin and --expect-sha256"
    [[ ${#WHEELS[@]} -eq 0 ]] \
        || fail "the read-back takes no files: it installs by pin, and the index is what it reads"
fi

cd "$REPO_ROOT"

# The local part is the build's own, and the row's label is only its head: the
# version scheme appends the clone's date and node after it, so a wheel built
# off a tag is recognised by its head and never by equality.
local_part_of() {
    local text="$1"
    [[ "$text" == *+* ]] || return 1
    text="${text##*+}"
    printf '%s' "${text%%-*}"
}

wheel_rows() {
    python3 packaging/flagcx/flagcx-config.py --list --channel wheel \
        | awk '$1 == "ready" {print $2}'
}

# --check-version-label reads backends.yaml alone; --build-inputs would run the
# matrix generator once per row for a fact already in the registry.
label_of_row() {
    python3 packaging/flagcx/flagcx-config.py --check-version-label "$1" \
        | sed -n 's/^ok: .*: label //p'
}

# A row owns a label when the label is that row's, or is that row's followed by
# the `<date>.<node>` the version scheme appends — the same tail
# build-flagcx-wheel.sh asserts by. Taking any dot-suffix instead would read a
# chip row's label as its base row's: `cann8.5.0` heads `cann8.5.0.910c.<date>`,
# so every pair of rows that differ only by a suffix would name two rows and
# neither artifact could be verified.
row_for_label() {
    local label="$1" key row_label tail match=""
    for key in $(wheel_rows); do
        row_label="$(label_of_row "$key")"
        # An empty one is a row whose label did not print, and every pattern
        # below would then match it.
        [[ -n "$row_label" ]] || continue
        if [[ "$label" == "$row_label" ]]; then
            tail=""
        elif [[ "$label" == "$row_label".* ]]; then
            tail="${label#"$row_label".}"
        else
            continue
        fi
        [[ -z "$tail" || "$tail" =~ ^[0-9]{8}\. ]] || continue
        [[ -z "$match" ]] \
            || fail "$label is published by both $match and $key, so the artifact names no single row"
        match="$key"
    done
    [[ -n "$match" ]] \
        || fail "no wheel row publishes the label $label — the artifact names no row in backends.yaml"
    printf '%s' "$match"
}

# The label is the only thing in either artifact that names the row which built
# it, and the row is what names the image and the device flags — so verifying a
# correct wheel against another backend's image would be a pass that says
# nothing. It is read off the artifact rather than trusted from the call site.
WANT_VERSION=""
if (( LOCAL_MODE )); then
    LABEL=""
    for wheel in "${WHEELS[@]}"; do
        [[ -f "$wheel" ]] || fail "$wheel: no such file"
        name="$(basename "$wheel")"
        case "$name" in
            flagcx-*-*-*-*.whl) ;;
            *) fail "$name: not a wheel name of the form flagcx-<version>-<pytag>-<abitag>-<platform>.whl" ;;
        esac
        local_label="$(local_part_of "$name")" \
            || fail "$name: no local part — every wheel this line builds stamps one, and without it the name is not this build's"
        [[ -z "$LABEL" || "$local_label" == "$LABEL" ]] \
            || fail "$name: label $local_label, but ${WHEELS[0]} carries $LABEL — two rows' wheels are in one verification"
        LABEL="$local_label"
        WANT_VERSION="${name#flagcx-}"; WANT_VERSION="${WANT_VERSION%%-*}"
    done
    # The pin names a version, so one row's two wheels are two artifacts no pin
    # can tell apart — and pip would install them over each other.
    [[ ${#WHEELS[@]} -eq 1 ]] \
        || fail "${#WHEELS[@]} wheels given: pass one, the one the pin will name"
    WHEEL="${WHEELS[0]}"
else
    [[ "$OPT_PIN" == flagcx==* ]] \
        || fail "--pin must be flagcx==<version>, got $OPT_PIN"
    WANT_VERSION="${OPT_PIN#flagcx==}"
    LABEL="$(local_part_of "$WANT_VERSION")" \
        || fail "--pin $OPT_PIN carries no local part, so it names every vendor's build of $WANT_VERSION"
    [[ "$OPT_EXPECT_SHA256" =~ ^[0-9a-f]{64}$ ]] \
        || fail "--expect-sha256 must be a sha256 in lowercase hex, got $OPT_EXPECT_SHA256"
fi

if [[ -n "$OPT_BACKEND" ]]; then
    KEY="$OPT_BACKEND"
else
    KEY="$(row_for_label "$LABEL")"
    echo ">>> $KEY: read off the artifact's label $LABEL"
fi

# Captured into a variable rather than inlined: `set -e` does not see a failure
# inside eval's command substitution, so an inline one would let the script run
# on with every WHEEL_* empty.
INPUTS="$(python3 packaging/flagcx/flagcx-config.py --build-inputs "$KEY" --channel wheel)"
set -a
eval "$INPUTS"
set +a

# A row's label heads the local part of every wheel it builds, so a wheel whose
# label does not is a wheel of another row: the image below is the wrong one, and
# so are the device flags.
case "$LABEL" in
    "$WHEEL_LOCAL_VERSION"|"$WHEEL_LOCAL_VERSION".*) ;;
    *) fail "$KEY publishes the label $WHEEL_LOCAL_VERSION, the artifact carries $LABEL" ;;
esac
# The runtime image is the delivery environment, and the build environment too on
# every row without a builder image. This is still where the wheel has to stand
# on its own: the builder is only ever a superset.
[[ -n "$WHEEL_IMAGE_TAG" ]] \
    || fail "$KEY: no runtime image in its matrix row, so there is nothing to verify in"
if [[ -n "$OPT_INDEX_URL" ]]; then
    # Both sides come off the same matrix row, so this holds by construction —
    # and it is what keeps a read-back from reporting on an index the row does
    # not publish to.
    [[ "$OPT_INDEX_URL" == "$WHEEL_INDEX_URL" ]] \
        || fail "--index-url $OPT_INDEX_URL is not this row's index ($WHEEL_INDEX_URL)"
fi

docker image inspect "$WHEEL_IMAGE_TAG" >/dev/null 2>&1 || docker pull "$WHEEL_IMAGE_TAG"

# The vendor's device passthrough, from build-config.yml: the extension this
# wheel installs links the vendor's communication library, so this container
# needs the flags a runtime container gets. Keyed on the backend key's prefix,
# not WHEEL_ADAPTOR: that is the FlagCX adaptor family, which is not the
# build-infra vendor wherever the adaptor carries its own name (iluvatar_corex,
# musa, tsm), and a miss fell back to run.default — leaving the device out of
# the container with no line in the log saying so. metax is why the chain ends at
# run.default -- its entry carries toolkit_cmd (a wrapper binary CI does not
# have) and raw, no toolkit.
RUN_FLAGS="$(BACKEND="$WHEEL_NAME" python3 - <<'PY'
import os
import yaml
with open(".github/build-config.yml") as fh:
    run = yaml.safe_load(fh).get("run") or {}
# base/<name> names a backend {vendor}-{backend}, so the prefix is the
# build-infra vendor name. There is no second copy to keep in step.
key = os.environ["BACKEND"]
entry = (run.get("vendors") or {}).get(key.split("-", 1)[0])
if entry is None:
    raise SystemExit(
        f"run.vendors in build-config.yml has no entry for {key!r} — refusing "
        f"to verify without the device flags its backend needs"
    )
print(entry.get("toolkit") or entry.get("raw") or run.get("default", ""))
PY
)"
# Adding it twice makes docker abort with "network host is specified multiple
# times", and some vendor toolkits already carry it.
if [[ " ${RUN_FLAGS} " != *" --network "* ]]; then
    RUN_FLAGS="${RUN_FLAGS} --network host"
fi

# The node's proxy, relayed the way the build relays it.
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

CONTAINER="flagcx-wheel-verify-$$"
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

# mode=local the wheel as a file: nothing may come from a network, so a pass
#            says the artifact is complete
# mode=index the wheel as the index serves it: the install has to come from the
#            pin, and the bytes have to be the ones that were built
verify_in() {
    local image="$1" mode="$2" in_container=""

    echo ">>> $mode: $image $RUN_FLAGS"
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$CONTAINER" $RUN_FLAGS "${PROXY_ENV[@]}" "$image" sleep infinity >/dev/null
    if [[ "$mode" == local ]]; then
        in_container="/tmp/wheels/$(basename "$WHEEL")"
        docker exec "$CONTAINER" mkdir -p /tmp/wheels
        docker cp "$WHEEL" "$CONTAINER:/tmp/wheels/"
    fi

    docker exec -i -e MODE="$mode" -e IMAGE="$image" -e WANT_VERSION="$WANT_VERSION" \
        -e WHEEL="$in_container" -e INDEX="$OPT_INDEX_URL" -e PIN="$OPT_PIN" \
        -e EXPECT_SHA="$OPT_EXPECT_SHA256" -e BITCODE_ARCH="$WHEEL_BITCODE_ARCH" \
        "$CONTAINER" bash -euo pipefail -s <<'IN_CONTAINER'
PY=/flagos/bin/python

# A vendor image prints on its own stdout the moment a package imports: on
# enflame-tops1.10.6, flagcx pulls in triton_kernel_gcu, which prints a line
# before flagcx's own. A plain command substitution folds that into the value,
# and a path read back with a word of prose in front of it is not a path — it
# read as a six-entry glob rather than as one directory. So a value taken off
# $PY names itself on the way out and is read back by that name.
py_value() {
    local marker="$1" code="$2" out n
    out="$("$PY" -c "$code")"
    n="$(printf '%s\n' "$out" | grep -c "^${marker}=" || true)"
    [ "$n" -eq 1 ] \
        || { echo "$PY printed $n $marker lines, not one: $out" >&2; exit 1; }
    printf '%s\n' "$out" | sed -n "s/^${marker}=//p"
}

# An importable flagcx is a different artifact: every assertion below would
# describe that copy while reading as a pass for this one. The container is a
# throwaway, so the preinstalled copy is uninstalled rather than the run being
# refused — the row's own runtime image may legitimately carry the wheel as a
# dep (nvidia-cuda13.3 installs it for PR #1266), and after the uninstall the
# assertions can describe this wheel alone. The image's working directory is
# left out of the probe — a source tree checked out there would answer it.
if (cd /tmp && "$PY" -c 'import flagcx') >/dev/null 2>&1; then
    echo "$IMAGE already carries a flagcx — uninstalling it so this wheel is the only artifact under test"
    "$PY" -m pip uninstall -y flagcx
fi

if [ "$MODE" = index ]; then
    : "${INDEX:?}" "${PIN:?}" "${EXPECT_SHA:?}"
    rm -rf /tmp/dl
    mkdir -p /tmp/dl
    # --no-cache-dir: a warm cache would answer this from an earlier run, and the
    # step is about what the index holds now.
    "$PY" -m pip download --no-deps --no-cache-dir --dest /tmp/dl --index-url "$INDEX" "$PIN"
    dl="$(ls -1 /tmp/dl)"
    [ "$(printf '%s\n' "$dl" | wc -l)" -eq 1 ] \
        || { echo "$INDEX: the pin resolved to $dl" >&2; exit 1; }
    # A space in the name is what a registry that decodes the local part's `+`
    # produces, and it is the failure no hash can show: the bytes are right and
    # the name a client asks for is not one any index can match.
    case "$dl" in
        *" "*) echo "$INDEX: serves '$dl', a name with a space in it — the + of the local part was decoded" >&2; exit 1 ;;
    esac
    case "$dl" in
        "flagcx-$WANT_VERSION-"*.whl) ;;
        *) echo "$INDEX: serves $dl, this build is flagcx-$WANT_VERSION" >&2; exit 1 ;;
    esac
    # The only check that says the index holds *this* artifact rather than a
    # rebuild that happens to carry the same name.
    got="$(sha256sum "/tmp/dl/$dl" | awk '{print $1}')"
    [ "$got" = "$EXPECT_SHA" ] \
        || { echo "$INDEX: serves $got, this build is $EXPECT_SHA" >&2; exit 1; }
    # By pin, not by the file just downloaded: the install is what a user does.
    # --no-deps so nothing the image already carries can satisfy the wheel.
    "$PY" -m pip install --no-deps --no-cache-dir --index-url "$INDEX" "$PIN"
    SOURCE="$INDEX"
else
    # --no-index: nothing here may come from a network, so a pass says the wheel
    # is complete rather than that an index filled a gap.
    "$PY" -m pip install --no-deps --no-index --no-cache-dir "$WHEEL"
    SOURCE="the wheel"
fi

installed="$(py_value FLAGCX_VERSION 'import importlib.metadata as m; print("FLAGCX_VERSION=" + m.version("flagcx"))')"
# An older release under the same pin would install and exit 0, reading as a
# pass.
[ "$installed" = "$WANT_VERSION" ] \
    || { echo "flagcx: $SOURCE installs $installed, this build is $WANT_VERSION" >&2; exit 1; }

site="$(py_value FLAGCX_SITE 'import os, flagcx; print("FLAGCX_SITE=" + os.path.dirname(os.path.dirname(flagcx.__file__)))')"
set -- $site/flagcx-*.dist-info
[ "$#" -eq 1 ] && [ -d "$1" ] \
    || { echo "flagcx: $# dist-info directories in $site, expected the one this install wrote" >&2; exit 1; }
metadata="$1/METADATA"

# The wheel declares no dependencies, and --no-deps is why a declared one is
# invisible to every other check here: the day a Requires-Dist appears is the day
# this package starts dragging something in behind it.
if grep -q '^Requires-Dist:' "$metadata"; then
    grep '^Requires-Dist:' "$metadata" >&2
    echo "$metadata: the wheel declares a dependency, and --no-deps is the only reason nothing pulled it in" >&2
    exit 1
fi

# The library is data in the wheel rather than an entry point, so it is the one
# part of the payload an install can drop without saying so.
lib="$site/flagcx/lib/libflagcx.so"
[ -f "$lib" ] \
    || { echo "flagcx: $lib is not on disk — the wheel's own payload did not survive the install" >&2; exit 1; }

# The device bitcode and its header, on the rows that publish them. No import
# reaches either: a wheel that dropped them installs and imports exactly like one
# that has them, and the loss would surface as another repo's build failing later.
if [ -n "${BITCODE_ARCH:-}" ]; then
    bc="$site/flagcx/lib/libflagcx_device.bc"
    hdr="$site/flagcx/include/flagcx_device_wrapper.h"
    for f in "$bc" "$hdr"; do
        [ -s "$f" ] \
            || { echo "flagcx: $f is missing or empty — the $BITCODE_ARCH device bitcode did not survive the install" >&2; exit 1; }
    done
    # Bitcode magic: the file being there is not the same as it being bitcode,
    # and a placeholder or a text file would pass every check above.
    [ "$(head -c 2 "$bc")" = "BC" ] \
        || { echo "flagcx: $bc does not start with the LLVM bitcode magic" >&2; exit 1; }
    echo ">>> device bitcode: $bc ($(stat -c%s "$bc") bytes, $BITCODE_ARCH) and $(basename "$hdr")"
fi

# ldd is a bash script and the import below is not: leaving the startup hook on
# would trace this against whatever /etc/profile.d re-exports, which is a list
# the interpreter never sees. Naming the unresolved library here is the point —
# the alternative is an ImportError that names nothing.
#
# The search path carries torch's own library directory, which is where `import
# torch` finds libc10/libtorch: a bare ldd calls those unresolved in a wheel that
# loads perfectly (measured on nvidia-cuda13.3).
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
IN_CONTAINER
}

verify_in "$WHEEL_IMAGE_TAG" "$([[ $LOCAL_MODE -eq 1 ]] && echo local || echo index)"

echo ">>> ok: flagcx $WANT_VERSION ($WHEEL_ARCH, $WHEEL_PYTHON_TAG)"
