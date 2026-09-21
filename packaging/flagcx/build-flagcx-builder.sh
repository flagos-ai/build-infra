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
# Build FlagCX build-toolchain images, one backend per container.
#
# Usage:
#   build-flagcx-builder.sh --list
#   build-flagcx-builder.sh --backend nvidia-cuda13.3
#   build-flagcx-builder.sh --all --push
#
# Options:
#   --backend KEY   backend from backends.yaml (repeatable)
#   --all           every builder-enabled backend
#   --list          one line per backend, on this channel or off it
#   --tag REF       build as REF instead of the row's own image ref
#   --push          push each image to the registry its ref names
#   --no-cache      pass --no-cache to docker build
#
# Why this is a script and not a workflow step: the same recipe has to run on a
# runner and on a developer's machine, and the only difference is whether the
# registry in front of docker is reachable.
#
# There is no --ref, unlike the deb and wheel lines: no FlagCX source goes into
# this image. It carries the toolchain the row's runtime image lacks, and the
# verification is what clones a ref and compiles into it.
#
# The image is tagged with its published ref rather than a local name that a
# second step renames, which is what scripts/build_runtime.py does too: the ref
# is derived in flagcx-config.py (builder_image) from the row and the registry, so
# the build and the verification arrive at the same string without either
# owning a spelling of it.
#
# LLVM_VERSION/LLVM_SHA256 are the one pin this line cannot do without, and they
# are constants here rather than build args with no owner: LLVM 22 is the floor
# for CUDA 13 device bitcode (see Containerfile.builder), so moving it is a
# decision rather than a parameter, and both NVIDIA rows take the same one.
# Overridable from the environment for the day the pin moves.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

LLVM_VERSION="${LLVM_VERSION:-22.1.8}"
LLVM_SHA256="${LLVM_SHA256:-df0e1ecf16caf3489a272a5eea4eec9b0d82878f6477fa309504f918a0006384}"

BACKENDS=()
BUILD_ALL=0
LIST=0
PUSH=0
NO_CACHE=0
OPT_TAG=""

usage() { sed -n '18,29p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend)  BACKENDS+=("${2:?--backend needs a key}"); shift 2 ;;
        --all)      BUILD_ALL=1; shift ;;
        --list)     LIST=1; shift ;;
        --tag)      OPT_TAG="${2:?--tag needs a ref}"; shift 2 ;;
        --push)     PUSH=1; shift ;;
        --no-cache) NO_CACHE=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *)          echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if (( LIST )); then
    exec python3 "$HERE/flagcx-config.py" --list --channel builder
fi
if (( BUILD_ALL )); then
    # Rows without a builder: block are excluded on purpose: absent means that
    # row's runtime image already carries what the FlagCX build needs, and --all
    # is what CI runs.
    while read -r state key _rest; do
        [[ "$state" == ready ]] && BACKENDS+=("$key")
    done <<< "$(python3 "$HERE/flagcx-config.py" --list --channel builder)"
fi
if [[ ${#BACKENDS[@]} -eq 0 ]]; then
    echo "nothing to build: pass --backend KEY, --all, or --list" >&2
    exit 2
fi
if [[ -n "$OPT_TAG" && ${#BACKENDS[@]} -ne 1 ]]; then
    echo "--tag names one image, so it takes one --backend" >&2
    exit 2
fi

# Drift between backends.yaml and the runtime matrix is cheaper to catch here
# than inside a docker build, where a row with no runtime image fails on a pull
# and names a ref rather than the row that produced it.
python3 "$HERE/flagcx-config.py" --check --channel builder >/dev/null

# git is the source of truth for the provenance labels, as in build_base.py and
# build_runtime.py: the image records where its recipe came from, not when it
# happened to be built.
revision="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
created="$(git -C "$REPO_ROOT" show -s --format=%cI HEAD 2>/dev/null || true)"

for key in "${BACKENDS[@]}"; do
    (
        set -a
        # Captured first, then eval'd, rather than `eval "$(python3 ...)"`: a
        # command substitution inside eval fails invisibly to `set -e`, and the
        # build would then proceed with every DEB_* empty.
        INPUTS="$(python3 "$HERE/flagcx-config.py" --build-inputs "$key" --channel builder)"
        eval "$INPUTS"
        set +a

        ref="${OPT_TAG:-$DEB_BUILDER_IMAGE}"
        [[ -n "$ref" ]] || { echo "$key: no image ref (see --check)" >&2; exit 1; }
        echo ">>> $key: $ref (from $DEB_IMAGE_TAG)"

        # The runtime image this is built on is a moving flat tag, so the ref
        # alone does not say which runtime the toolchain was laid over. The
        # digest does, and it is what the wheel build will compare against when
        # the staleness question becomes its own (see WHEEL-DESIGN.md).
        # Absent rather than wrong for a locally built runtime image, which has
        # no RepoDigests at all.
        base_digest="$(docker image inspect \
            --format '{{range .RepoDigests}}{{println .}}{{end}}' "$DEB_IMAGE_TAG" \
            2>/dev/null | head -n1 || true)"

        labels=(
            --label "org.opencontainers.image.version=$DEB_VERSION"
            --label "org.opencontainers.image.source=https://github.com/flagos-ai/build-infra"
            # Which row this toolchain was assembled for. Two builders for the
            # same vendor are near-identical 17 GB images, and the runtime ref
            # alone does not say which row's SDK apt list went in.
            --label "flagos.backend=$key"
            --label "flagos.base=$DEB_IMAGE_TAG"
            --label "flagos.llvm.version=$LLVM_VERSION"
            --label "flagos.llvm.sha256=$LLVM_SHA256"
        )
        [[ -n "$revision" ]] && labels+=(--label "org.opencontainers.image.revision=$revision")
        [[ -n "$created" ]] && labels+=(--label "org.opencontainers.image.created=$created")
        [[ -n "$base_digest" ]] && labels+=(--label "flagos.base_digest=$base_digest")

        cache_arg=(); (( NO_CACHE )) && cache_arg=(--no-cache)

        # The node's proxy, relayed the way the other image builds relay it:
        # the LLVM tarball is fetched during the build, and the aarch64 nodes
        # have no direct egress at all. A bare --build-arg NAME takes its value
        # from this script's environment and never from the command line — the
        # node's process table is readable by every user on it.
        proxy_arg=()
        for pair in http_proxy:HTTP_PROXY https_proxy:HTTPS_PROXY no_proxy:NO_PROXY; do
            lower="${pair%%:*}"; upper="${pair##*:}"
            value="$(printenv "$lower" || true)"
            [ -n "$value" ] || value="$(printenv "$upper" || true)"
            if [ -n "$value" ]; then
                export "${lower}=${value}"
                proxy_arg+=(--build-arg "$lower")
            fi
        done

        # --network host: the build's only network use is the LLVM download, and
        # the default bridge on the runners intermittently cannot open a TCP
        # connection to github.com while the host can (measured on metax124 for
        # the wheel line's clone: 1 of 2 bridge attempts failed, 2 of 2 host
        # attempts succeeded).
        #
        # A failing step makes BuildKit echo the resolved RUN command, so the
        # relayed proxy's userinfo would land in whatever captures this stdout.
        # Redacted in the pipe; pipefail still carries docker's own status.
        docker build \
            "${cache_arg[@]}" \
            "${proxy_arg[@]}" \
            "${labels[@]}" \
            --network host \
            --build-arg "BASE_IMAGE=$DEB_IMAGE_TAG" \
            --build-arg "DEB_APT=$DEB_APT" \
            --build-arg "DEB_BUILDER_APT=$DEB_BUILDER_APT" \
            --build-arg "DEB_ASSERT=$DEB_ASSERT" \
            --build-arg "LLVM_VERSION=$LLVM_VERSION" \
            --build-arg "LLVM_SHA256=$LLVM_SHA256" \
            -t "$ref" \
            -f "$HERE/Containerfile.builder" \
            "$REPO_ROOT" 2>&1 \
            | awk '{gsub(/:\/\/[^@\/ ]+:[^@\/ ]+@/, "://[redacted]@"); print; fflush()}'

        # Reported rather than pushed by default: the image is the input to
        # something else, and pushing an unverified one is what the workflow's
        # verify job exists to prevent.
        if (( PUSH )); then
            echo ">>> pushing $ref"
            docker push "$ref"
        fi
        echo ">>> built $ref"
    )
done
