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

# Build the flag-gems-cpp-<vendor> wheel inside the runtime:v1 container.
# Env vars (all required):
#   FLAGGEMS_REF                — git tag, e.g. "v5.3.1"
#   FLAGGEMS_CPP_VENDOR         — set_cpp_vendor.sh arg, e.g. "cuda"
#   FLAGGEMS_CMAKE_ARGS         — cmake defines
#   SETUPTOOLS_SCM_PRETEND_VERSION  — e.g. "5.3.1"
#   FLAGGEMS_BUILD_DEPS         — space-separated pip install specs

set -euo pipefail

# ── self-bootstrap git (base images are rebuilt infrequently) ──
if ! command -v git >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq --no-install-recommends git ca-certificates
fi

OUTDIR="${OUTDIR:-/tmp/wheel-out}"
FLAGGEMS_REPO="${FLAGGEMS_REPO:-https://github.com/flagos-ai/FlagGems.git}"

# ── clone + checkout ──────────────────────────────────────────
# Retry: h20 and other CN runners may have spotty GitHub connectivity.
clone_with_retry() {
  for i in 1 2 3; do
    if git clone --quiet "$FLAGGEMS_REPO" /tmp/FlagGems 2>/dev/null; then
      return 0
    fi
    echo "git clone attempt $i failed, retrying in 30s..."
    sleep 30
  done
  return 1
}

clone_with_retry
cd /tmp/FlagGems
git fetch --quiet --tags origin tag "$FLAGGEMS_REF" 2>/dev/null \
  || git fetch --quiet --tags --force origin
git checkout --quiet --detach "$FLAGGEMS_REF"
echo "FlagGems @ $(git describe --tags 2>/dev/null || echo "$FLAGGEMS_REF")"

# ── set vendor + install build deps ───────────────────────────
tools/set_cpp_vendor.sh "$FLAGGEMS_CPP_VENDOR"
if [ -n "${FLAGGEMS_BUILD_DEPS:-}" ]; then
  # shellcheck disable=SC2086
  pip install $FLAGGEMS_BUILD_DEPS
fi

# ── build ─────────────────────────────────────────────────────
mkdir -p "$OUTDIR"
pip wheel ./cpp --no-deps -w "$OUTDIR"

# ── install + inspect .so ─────────────────────────────────────
pip install --no-deps "$OUTDIR"/*.whl
SO=$(find "$VIRTUAL_ENV" -name 'c_operators*.so' 2>/dev/null | head -1)
if [ -z "$SO" ]; then
  echo "ERROR: c_operators .so not found in venv" >&2
  exit 1
fi
echo ".so path: $SO"
echo ">>> DT_NEEDED:"
readelf -d "$SO" | grep 'NEEDED' | sed 's/.*\[//;s/\]//' | sort
echo ">>> rpath / runpath:"
readelf -d "$SO" | grep -iE 'RPATH|RUNPATH' || echo "  (none — relies on LD_LIBRARY_PATH)"
echo "OK  cpp extension .so built for $FLAGGEMS_CPP_VENDOR"
