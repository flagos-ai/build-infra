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

# Build the pure-Python flag_gems wheel from FlagGems source.
#
# The wheel is platform-independent (py3-none-any) — no vendor toolchain needed,
# so this is a plain script, not a container build. The version comes from
# FlagGems' own setuptools_scm (git tags), so the checkout must include tags.
#
# Uploading is the workflow's job; this only builds. Output: $OUTDIR/*.whl.
#
#   FLAGGEMS_REF=<ref> ./build.sh          # build from a ref
#   OUTDIR=/tmp/wheels ./build.sh          # choose output dir
#   FLAGGEMS_REPO=/path/to/FlagGems ./build.sh   # build from a local clone
set -euo pipefail

FLAGGEMS_REPO="${FLAGGEMS_REPO:-https://github.com/flagos-ai/FlagGems.git}"
FLAGGEMS_REF="${FLAGGEMS_REF:-master}"
OUTDIR="${OUTDIR:-$(pwd)/wheels}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
src="$workdir/FlagGems"

echo ">>> cloning FlagGems @ ${FLAGGEMS_REF} (with tags, for setuptools_scm)"
git clone --quiet "$FLAGGEMS_REPO" "$src"
git -C "$src" fetch --quiet --tags --force origin || true
git -C "$src" checkout --quiet "$FLAGGEMS_REF"

echo ">>> version: $(git -C "$src" describe --tags 2>/dev/null || echo '(no tag)')"

echo ">>> building pure-Python wheel"
mkdir -p "$OUTDIR"
python3 -m pip wheel "$src" --no-deps -w "$OUTDIR"

wheel="$(ls -t "$OUTDIR"/flag_gems-*.whl 2>/dev/null | head -1)"
if [ -z "$wheel" ]; then
  echo "ERROR: no flag_gems wheel produced" >&2
  exit 1
fi
# Sanity: the pure-Python wheel must be py3-none-any. A platform tag means the
# build hit the C++ backend (wrong ref / packaging) — fail loudly.
case "$wheel" in
  *-py3-none-any.whl) : ;;
  *) echo "ERROR: expected a py3-none-any wheel, got $(basename "$wheel")" >&2
     echo "       (is FLAGGEMS_REF on the pure-Python packaging branch?)" >&2
     exit 1 ;;
esac

echo ">>> built: $(basename "$wheel")"
