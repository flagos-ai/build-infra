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
# Build FlagCX .deb packages, one backend per container.
#
# Usage:
#   build-flagcx-deb.sh --list
#   build-flagcx-deb.sh --backend metax-maca3.8.1.3
#   build-flagcx-deb.sh --all
#
# Options:
#   --backend KEY   backend from backends.yaml (repeatable)
#   --all           every enabled backend
#   --list          one line per backend, ready or probe-pending
#   --ref REF       FlagCX git ref to build
#   --src DIR       FlagCX checkout to derive --ref from
#                   (default $FLAGCX_SRC; required unless --ref is given)
#   --repo URL      FlagCX repository to clone from
#   --out DIR       where the .deb files land (default ./dist)
#   --no-cache      pass --no-cache to docker build
#
# Why this is a script and not a workflow step: the same recipe has to run on a
# runner and on a developer's machine, and the only difference is whether there
# is a registry in front of docker.
#
# --ref is deliberately not defaulted to a branch. A .deb is a release artifact,
# so a build from a moving branch is a mistake worth a warning: --src derives
# the tag HEAD sits on, and the fallback to a branch says so on stderr.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

BACKENDS=()
BUILD_ALL=0
LIST=0
OPT_REF=""
OPT_SRC="${FLAGCX_SRC:-}"
OPT_REPO="https://github.com/flagos-ai/FlagCX.git"
OPT_OUT="$PWD/dist"
NO_CACHE=0
FALLBACK_REF="main"

usage() { sed -n '16,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend)  BACKENDS+=("${2:?--backend needs a key}"); shift 2 ;;
        --all)      BUILD_ALL=1; shift ;;
        --list)     LIST=1; shift ;;
        --ref)      OPT_REF="${2:?--ref needs a value}"; shift 2 ;;
        --src)      OPT_SRC="${2:?--src needs a directory}"; shift 2 ;;
        --repo)     OPT_REPO="${2:?--repo needs a URL}"; shift 2 ;;
        --out)      OPT_OUT="${2:?--out needs a directory}"; shift 2 ;;
        --no-cache) NO_CACHE=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *)          echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if (( LIST )); then
    exec python3 "$HERE/deb-config.py" --list
fi
if (( BUILD_ALL )); then
    # Probe-pending backends are excluded on purpose: they are excluded because
    # nobody has confirmed their SDK paths yet, and --all is what CI runs.
    while read -r state key _rest; do
        [[ "$state" == ready ]] && BACKENDS+=("$key")
    done <<< "$(python3 "$HERE/deb-config.py" --list)"
fi
if [[ ${#BACKENDS[@]} -eq 0 ]]; then
    echo "nothing to build: pass --backend KEY, --all, or --list" >&2
    exit 2
fi

# Drift between backends.yaml and the runtime matrix is cheaper to catch here
# than three layers down in dpkg-buildpackage.
python3 "$HERE/deb-config.py" --check >/dev/null

resolve_ref() {
    if [[ -n "$OPT_REF" ]]; then
        printf '%s\n' "$OPT_REF"
        return
    fi
    if [[ -z "$OPT_SRC" ]]; then
        echo "--ref is required when there is no FlagCX checkout (\$FLAGCX_SRC or --src)" >&2
        exit 2
    fi
    local tag
    if tag="$(git -C "$OPT_SRC" describe --tags --exact-match 2>/dev/null)"; then
        printf '%s\n' "$tag"
        return
    fi
    echo "warning: $OPT_SRC HEAD is not at a tag; building branch $FALLBACK_REF," \
         "which is not reproducible" >&2
    printf '%s\n' "$FALLBACK_REF"
}

FLAGCX_REF="$(resolve_ref)"
mkdir -p "$OPT_OUT"
OPT_OUT="$(cd "$OPT_OUT" && pwd)"

for key in "${BACKENDS[@]}"; do
    # The join is done here, on the host, and debian/control is written into the
    # host debian/ dir, which the Containerfile's overlay copy carries in. It is
    # one file, so backends are built one at a time — a parallel build would hand
    # two containers the same tree.
    (
        set -a
        # Captured first, then eval'd, rather than `eval "$(python3 ...)"`: a
        # command substitution inside eval fails invisibly to `set -e`, and the
        # build would then proceed with every DEB_* empty. eval and not
        # `. <(...)`, which is bash-4 and sources nothing at all on bash 3.2;
        # deb-config.py shell-quotes every value, so there is nothing here for
        # eval to reinterpret.
        INPUTS="$(python3 "$HERE/deb-config.py" --build-inputs "$key")"
        eval "$INPUTS"
        set +a

        python3 "$HERE/deb-config.py" --render-control "$HERE/debian/control"

        tag="flagcx-deb:$key"
        echo ">>> $key: $DEB_PACKAGE ($DEB_ARCH, glibc >= $DEB_GLIBC_FLOOR) from $FLAGCX_REF"

        cache_arg=(); (( NO_CACHE )) && cache_arg=(--no-cache)

        # The runner's proxy is not forwarded into builds, and the aarch64 nodes
        # have no direct egress at all — without this the toolchain apt layer
        # cannot reach the archive. Same relay as scripts/build_runtime.py,
        # emitted lowercase because that is the casing apt reads and the one the
        # runners export.
        #
        # no_proxy rides along because it is what keeps the mirror off the proxy:
        # relayed without it, apt sends mirrors.aliyun.com through a proxy that
        # answers 502 — measured on enflame, where the same fetch is 200 direct.
        proxy_arg=()
        for pair in http_proxy:HTTP_PROXY https_proxy:HTTPS_PROXY no_proxy:NO_PROXY; do
            lower="${pair%%:*}"; upper="${pair##*:}"
            value="$(printenv "$lower" || true)"
            [ -n "$value" ] || value="$(printenv "$upper" || true)"
            if [ -n "$value" ]; then proxy_arg+=(--build-arg "${lower}=${value}"); fi
        done

        # --network host: the build's only network use is the clone, and the
        # default bridge on the runners intermittently cannot open a TCP
        # connection to github.com while the host can (measured on metax124:
        # 1 of 2 bridge clones failed at connect after 130s, 2 of 2 host clones
        # succeeded in 12s). Isolation buys nothing here and costs the rebuild.
        docker build \
            "${cache_arg[@]}" \
            "${proxy_arg[@]}" \
            --network host \
            --build-arg "BASE_IMAGE=$DEB_BASE_IMAGE" \
            --build-arg "FLAGCX_REPO=$OPT_REPO" \
            --build-arg "FLAGCX_REF=$FLAGCX_REF" \
            --build-arg "BACKEND=$key" \
            --build-arg "DEB_APT=$DEB_APT" \
            --build-arg "DEB_ASSERT=$DEB_ASSERT" \
            --build-arg "DEB_MAKE_FLAG=$DEB_MAKE_FLAG" \
            --build-arg "DEB_MAKE_ENV=$DEB_MAKE_ENV" \
            --build-arg "DEB_VENDOR_LIBS=$DEB_VENDOR_LIBS" \
            --build-arg "DEB_VENDOR_LIB_DIRS=$DEB_VENDOR_LIB_DIRS" \
            -t "$tag" \
            -f "$HERE/Containerfile.deb" \
            "$REPO_ROOT"

        # Same extraction idiom as packaging/flagtree and packaging/megatron:
        # a single-stage build, so the artifacts are read out of the image.
        cid="$(docker create "$tag")"
        docker cp "$cid:/output/." "$OPT_OUT/" && docker rm "$cid"
    )
done

echo ">>> artifacts in $OPT_OUT"
ls -1 "$OPT_OUT"/*.deb
