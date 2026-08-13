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

# All pip/python work goes through an isolated venv: on Ubuntu 24.04 (Python
# 3.12) the system interpreter is PEP 668 externally-managed and pip refuses to
# run against it. The venv lives in the throwaway workdir and dies with it.
python3 -m venv "$workdir/venv"
py="$workdir/venv/bin/python"

echo ">>> cloning FlagGems @ ${FLAGGEMS_REF} (with tags, for setuptools_scm)"
git clone --quiet "$FLAGGEMS_REPO" "$src"
git -C "$src" fetch --quiet --tags --force origin || true
git -C "$src" checkout --quiet "$FLAGGEMS_REF"

# The version is a pure function of git state, letting setuptools_scm read the
# tags in this clone. Two cases:
#
#   * HEAD is on an exact tag (release, ref=v5.3.4): the wheel is that tag,
#     clean — 5.3.4. This is what the release workflow means: you named a tag,
#     you get that exact wheel.
#   * HEAD is past the last tag (daily off master): date-stamp the next release
#     so builds are human-sortable and `pip install --pre` picks the newest —
#     5.3.5.dev20260809.
#
# We pin the daily version with a throwaway LOCAL tag on HEAD (never pushed,
# dies with the clone) rather than SETUPTOOLS_SCM_PRETEND_VERSION, which would
# make scm skip git and drop __commit_id__. The tag keeps scm reading git, so
# flag_gems/_version.py carries BOTH the date version and the real commit:
#
#   python -c "import flag_gems._version as v; print(v.version, v.commit_id)"
"$py" -m pip install --quiet "setuptools-scm>=8,<10"
if ! git -C "$src" describe --tags --exact-match >/dev/null 2>&1; then
  # guess-next-dev bumps to the next release after the latest tag (dist>0).
  # Strip the trailing .devN/.postN scm appends, leaving a bare base to stamp.
  base="$("$py" -c "
import setuptools_scm
v = setuptools_scm.get_version(
    root='$src',
    version_scheme='guess-next-dev',
    local_scheme='no-local-version',
)
print(v.split('.dev')[0].split('.post')[0])
")"
  git -C "$src" tag -f "${base}.dev$(date +%Y%m%d)" >/dev/null
fi
echo ">>> version: $(git -C "$src" describe --tags)  (commit $(git -C "$src" rev-parse --short=9 HEAD))"

echo ">>> building pure-Python wheel"
mkdir -p "$OUTDIR"
"$py" -m pip wheel "$src" --no-deps -w "$OUTDIR"

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
