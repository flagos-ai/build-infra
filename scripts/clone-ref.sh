#!/usr/bin/env bash
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

# Shallow-clone a component repository at a ref for the release workflows.
#
#   clone-ref.sh [--submodules] <repo_url> <ref> <dir>
#
# <ref> is a branch or tag name, or `pull/<N>` for the head of an open pull
# request. The pull form lets a packaging fix be built and verified through
# the real release path before it is merged; it is never publishable (the
# workflows refuse it when `publish` is set) and never carries a version of
# its own, since a pull request head is not a release.
set -euo pipefail

submodules=false
if [ "${1:-}" = "--submodules" ]; then
  submodules=true
  shift
fi
if [ $# -ne 3 ]; then
  echo "usage: $0 [--submodules] <repo_url> <ref> <dir>" >&2
  exit 2
fi
url=$1
ref=$2
dir=$3

if [[ "$ref" =~ ^pull/[0-9]+$ ]]; then
  # `git clone --branch` only takes a branch or tag, so clone the default
  # branch and fetch the pull request head on top of it.
  git clone --depth 1 --no-checkout "$url" "$dir"
  git -C "$dir" fetch --depth 50 origin "refs/${ref}/head"
  git -C "$dir" checkout -q --detach FETCH_HEAD
  if $submodules; then
    git -C "$dir" submodule update --init --recursive --depth 1
  fi
else
  args=(--depth 50 --branch "$ref")
  if $submodules; then
    args+=(--recurse-submodules --shallow-submodules)
  fi
  git clone "${args[@]}" "$url" "$dir"
fi
echo "Cloned ${ref} = $(git -C "$dir" rev-parse HEAD)"
