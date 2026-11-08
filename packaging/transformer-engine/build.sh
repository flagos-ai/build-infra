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

# Build the pure-Python TransformerEngine-FL wheel (the plugin dispatch layer).
#
# TE_FL_SKIP_CUDA=1 makes setup.py emit no native extensions (ext_modules=[]),
# so the wheel is platform-independent (py3-none-any) and needs no vendor
# toolchain — a plain script, not a container build. Only the FL (FlagGems /
# Triton) and reference backends live in this wheel; a vendor's own native TE
# (transformer_engine_<vendor>) and FlagGems are discovered at runtime, not
# bundled here. See DESIGN.md.
#
# This line is NON-NVIDIA ONLY. On NVIDIA the native kernels ARE stock TE and
# the dispatch layer buys nothing (it would even default to the slower flagos
# path), so NVIDIA uses the official TransformerEngine instead — see DESIGN.md.
#
# Version: TE-FL carries no setuptools_scm; te_version.py reads
# build_tools/VERSION.txt. That file holds only the upstream TE version on every
# tag (e.g. v2.17.0+fl.0.3.0 has VERSION.txt=2.17.0), and the FL version lives in
# the tag name alone. So the full wheel version `<upstream>+fl.<flver>` is
# produced HERE, by writing it into VERSION.txt of the throwaway clone before the
# build. The string is the release tag minus its leading `v` (or TE_FL_VERSION if
# set). NVTE_RELEASE_BUILD=1 then stops te_version.py appending a +<sha>, which
# would make a second `+` (invalid PEP 440).
#
# Uploading is the workflow's job; this only builds. Output: $OUTDIR/*.whl.
#
#   TE_FL_REF=v2.17.0+fl.0.3.0 ./build.sh         # build from a release tag
#   TE_FL_VERSION=2.17.0+fl.0.3.0 ./build.sh      # or state the version outright
#   OUTDIR=/tmp/wheels ./build.sh                 # choose output dir
#   TE_FL_REPO=/path/to/TransformerEngine-FL ./build.sh   # from a local clone
set -euo pipefail

TE_FL_REPO="${TE_FL_REPO:-https://github.com/flagos-ai/TransformerEngine-FL.git}"
TE_FL_REF="${TE_FL_REF:-main}"
OUTDIR="${OUTDIR:-$(pwd)/wheels}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
src="$workdir/TransformerEngine-FL"

# All pip/python work goes through an isolated venv: on Ubuntu 24.04 (Python
# 3.12) the system interpreter is PEP 668 externally-managed and pip refuses to
# run against it. The venv lives in the throwaway workdir and dies with it.
python3 -m venv "$workdir/venv"
py="$workdir/venv/bin/python"

echo ">>> cloning TransformerEngine-FL @ ${TE_FL_REF} (with tags)"
git clone --quiet "$TE_FL_REPO" "$src"
git -C "$src" fetch --quiet --tags --force origin || true
git -C "$src" checkout --quiet "$TE_FL_REF"

# Resolve the full wheel version `<upstream>+fl.<flver>`.
#   * TE_FL_VERSION given  -> use it verbatim.
#   * HEAD on an exact tag  -> the tag minus its leading `v` (release case).
#   * otherwise             -> refuse: a release wheel's version must be a
#     function of the ref, never guessed, so a non-tag build has to be told.
version="${TE_FL_VERSION:-}"
if [ -z "$version" ]; then
  if tag="$(git -C "$src" describe --tags --exact-match 2>/dev/null)"; then
    version="${tag#v}"
  else
    echo "ERROR: HEAD is not on an exact tag and TE_FL_VERSION is unset." >&2
    echo "       Pass TE_FL_REF=<release tag> or TE_FL_VERSION=<x.y.z+fl.a.b.c>." >&2
    exit 1
  fi
fi

# The FL build must declare its FL version — a bare upstream string (2.17.0, no
# +fl.<flver>) would be indistinguishable from stock TE on the index and defeats
# the local-label ownership guard. Refuse it.
case "$version" in
  *+*fl.*) : ;;
  *) echo "ERROR: version '$version' carries no '+fl.<flver>' local label." >&2
     echo "       The FL version is what tells this wheel apart from stock TE." >&2
     exit 1 ;;
esac

echo ">>> version: $version  (commit $(git -C "$src" rev-parse --short=9 HEAD))"
echo "$version" > "$src/build_tools/VERSION.txt"

echo ">>> building pure-Python wheel (TE_FL_SKIP_CUDA=1, NVTE_RELEASE_BUILD=1)"
mkdir -p "$OUTDIR"
TE_FL_SKIP_CUDA=1 NVTE_RELEASE_BUILD=1 NVTE_NO_LOCAL_VERSION=1 \
  "$py" -m pip wheel "$src" --no-deps -w "$OUTDIR"

wheel="$(ls -t "$OUTDIR"/transformer_engine-*.whl 2>/dev/null | head -1)"
if [ -z "$wheel" ]; then
  echo "ERROR: no transformer_engine wheel produced" >&2
  exit 1
fi

# Sanity 1: the dispatch wheel must be py3-none-any. A platform/ABI tag means
# TE_FL_SKIP_CUDA did not take and a native extension was compiled in — fail
# loudly rather than ship a per-node binary onto every vendor index.
case "$wheel" in
  *-py3-none-any.whl) : ;;
  *) echo "ERROR: expected a py3-none-any wheel, got $(basename "$wheel")" >&2
     echo "       (did TE_FL_SKIP_CUDA=1 reach setup.py?)" >&2
     exit 1 ;;
esac

# Sanity 2: the version in the filename must be the one we asked for, local
# label included. PEP 440 normalizes `+` runs, so compare on the normalized form.
norm="$("$py" -c "from packaging.utils import canonicalize_version as c; print(c('$version'))" 2>/dev/null || echo "$version")"
case "$(basename "$wheel")" in
  transformer_engine-"$version"-*|transformer_engine-"$norm"-*) : ;;
  *) echo "ERROR: wheel version != requested '$version': $(basename "$wheel")" >&2
     exit 1 ;;
esac

echo ">>> built: $(basename "$wheel")"
