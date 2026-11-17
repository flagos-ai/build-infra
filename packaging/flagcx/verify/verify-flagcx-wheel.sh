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
# Verify a FlagCX wheel as a file, and as the vendor index serves it. Both run
# in the row's builder image: this is the wheel line, and a row's runtime cannot
# exist yet — it pins this very wheel in `deps:`, so verifying there would be the
# circle. Whether the wheel loads in the delivered set is the runtime line's
# question (`verify_runtime.py` imports flagcx on every row that pins it), and it
# is asked there, after the runtime image is built.
#
# Usage:
#   verify-flagcx-wheel.sh --wheel dist/*.whl
#   verify-flagcx-wheel.sh --index-url "$matrix.flagos_pypi" --pin "$WHEEL_PIN" \
#       --expect-sha256 "$WHEEL_SHA256"
#
# Options:
#   --wheel            install the wheel by file path
#   --index-url URL    install by pin from this index
#   --pin PIN          `flagcx==<public>+<local>`, the version the index holds
#   --expect-sha256 H  sha256 of the wheel that was built
#   --backend KEY      backend from backends.yaml; read off the artifact when
#                      this is absent
#   --no-bitcode       skip the .bc assertions for a ref that carries no bitcode
#   --keep             leave the container behind for inspection
#   -h, --help         this text

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"

OPT_INDEX_URL=""
OPT_PIN=""
OPT_EXPECT_SHA256=""
OPT_BACKEND=""
LOCAL_MODE=0
KEEP=0
NO_BITCODE=0
WHEELS=()

usage() { sed -n '16,34p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

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
        --no-bitcode)     NO_BITCODE=1; shift ;;
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

label_of_row() {
    python3 packaging/flagcx/flagcx-config.py --check-version-label "$1" \
        | sed -n 's/^ok: .*: label //p'
}

row_for_label() {
    local label="$1" key row_label tail match=""
    for key in $(wheel_rows); do
        row_label="$(label_of_row "$key")"
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

# `set -e` does not see a failure inside eval's command substitution.
INPUTS="$(python3 packaging/flagcx/flagcx-config.py --build-inputs "$KEY" --channel wheel)"
set -a
eval "$INPUTS"
set +a
(( NO_BITCODE )) && WHEEL_BITCODE_ARCH=""

case "$LABEL" in
    "$WHEEL_LOCAL_VERSION"|"$WHEEL_LOCAL_VERSION".*) ;;
    *) fail "$KEY publishes the label $WHEEL_LOCAL_VERSION, the artifact carries $LABEL" ;;
esac

if (( LOCAL_MODE )); then
    IMAGE="$WHEEL_BUILDER_IMAGE"; MODE=local
else
    IMAGE="$WHEEL_BUILDER_IMAGE"; MODE=index
fi
[[ -n "$IMAGE" ]] \
    || fail "$KEY: its matrix row names no $MODE image, so there is nothing to verify in"
if [[ -n "$OPT_INDEX_URL" ]]; then
    [[ "$OPT_INDEX_URL" == "$WHEEL_INDEX_URL" ]] \
        || fail "--index-url $OPT_INDEX_URL is not this row's index ($WHEEL_INDEX_URL)"
fi

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"

RUN_FLAGS="$(python3 packaging/flagcx/flagcx-config.py --run-flags "$WHEEL_NAME")"

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

MOUNT_ARGS=()
WHEEL_IN_CONTAINER=""
if (( LOCAL_MODE )); then
    WHEEL_DIR="$(cd "$(dirname "$WHEEL")" && pwd)"
    WHEEL_IN_CONTAINER="/wheels/$(basename "$WHEEL")"
    MOUNT_ARGS=(-v "$WHEEL_DIR:/wheels:ro")
fi

echo ">>> $MODE: $IMAGE $RUN_FLAGS"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" $RUN_FLAGS "${PROXY_ENV[@]}" \
    "${MOUNT_ARGS[@]}" \
    -v "$HERE/verify-flagcx-wheel-in-container.sh:/verify.sh:ro" \
    "$IMAGE" sleep infinity >/dev/null

docker exec -i -e MODE="$MODE" -e WANT_VERSION="$WANT_VERSION" \
    -e WHEEL="$WHEEL_IN_CONTAINER" -e INDEX="$OPT_INDEX_URL" -e PIN="$OPT_PIN" \
    -e EXPECT_SHA="$OPT_EXPECT_SHA256" -e BITCODE_ARCH="$WHEEL_BITCODE_ARCH" \
    "$CONTAINER" bash /verify.sh

echo ">>> ok: flagcx $WANT_VERSION ($WHEEL_ARCH, $WHEEL_PYTHON_TAG)"
