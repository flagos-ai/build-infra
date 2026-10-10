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

# Build the pure-Python flagos-compressor wheel from the upstream release tag.
#
# The wheel is platform-independent (py3-none-any, ~100 KB, no C extension),
# so this is a plain venv script, not a container build — same shape as
# packaging/flaggems/build.sh. Version is static in pyproject.toml.
#
#   REF=<ref> ./build.sh            # build from a ref (default: v0.1.0)
#   OUTDIR=/tmp/wheels ./build.sh   # choose output dir
set -euo pipefail

REPO="${REPO:-https://github.com/flagos-ai/FlagOS-Compressor.git}"
REF="${REF:-v0.1.0}"
OUTDIR="${OUTDIR:-$(pwd)/wheels}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
src="$workdir/FlagOS-Compressor"

python3 -m venv "$workdir/venv"
py="$workdir/venv/bin/python"

echo ">>> cloning FlagOS-Compressor @ ${REF}"
git clone --quiet --depth 1 --branch "$REF" "$REPO" "$src"

mkdir -p "$OUTDIR"
"$py" -m pip wheel "$src" --no-deps --no-build-isolation -w "$OUTDIR"

wheel="$(ls -t "$OUTDIR"/flagos_compressor-*.whl 2>/dev/null | head -1)"
if [ -z "$wheel" ]; then
  echo "ERROR: no flagos-compressor wheel produced" >&2
  exit 1
fi
case "$wheel" in
  *-py3-none-any.whl) : ;;
  *) echo "ERROR: expected py3-none-any, got $(basename "$wheel")" >&2; exit 1 ;;
esac

echo ">>> built: $(basename "$wheel")"
