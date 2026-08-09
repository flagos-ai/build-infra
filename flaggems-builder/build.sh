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

# Daily builds get a date-stamped version instead of the scm default
# (e.g. 5.4.0.dev580+gb89e0aeb8), whose leading token is a commit *count* —
# opaque about when the wheel was built. We swap the count for the build date:
#
#   5.3.5.dev20260809
#   \______/ \______/
#    base     build date
#
# The date makes builds human-sortable and lets `pip install --pre` always pick
# the newest (PEP 440 orders by version, and version order == chronological
# order here). One scheduled build per day, so a bare date never collides on
# the index; a manual same-day rebuild should pass FLAGGEMS_VERSION to override.
#
# We apply this version by creating a throwaway LOCAL git tag on HEAD rather
# than the SETUPTOOLS_SCM_PRETEND_VERSION env var. The env var makes scm skip
# git entirely, leaving __commit_id__ = None in _version.py. Tagging keeps scm
# reading git, so the generated flag_gems/_version.py carries BOTH the date
# version and the real commit: a tester can recover the commit at runtime via
#
#   python -c "import flag_gems._version as v; print(v.version, v.commit_id)"
#
# The tag lives only in this throwaway clone (never pushed) and dies with it.
#
# Set FLAGGEMS_VERSION to override the computed version (e.g. a pinned build).
if [ -z "${FLAGGEMS_VERSION:-}" ]; then
  python3 -m pip install --quiet "setuptools-scm>=8,<10"
  # guess-next-dev bumps to the next release after the latest tag (dist>0), so
  # once v5.3.4 is tagged and any commit lands the base becomes 5.3.5. Strip the
  # trailing .devN/.postN scm appends, leaving a bare base for our date stamp.
  base="$(python3 -c "
import setuptools_scm
v = setuptools_scm.get_version(
    root='$src',
    version_scheme='guess-next-dev',
    local_scheme='no-local-version',
)
print(v.split('.dev')[0].split('.post')[0])
")"
  FLAGGEMS_VERSION="${base}.dev$(date +%Y%m%d)"
fi
# Local, unpushed tag on HEAD: scm reads it as the exact version while still
# recording the commit. -f so a re-run in a reused clone overwrites cleanly.
git -C "$src" tag -f "$FLAGGEMS_VERSION" >/dev/null
echo ">>> daily version: ${FLAGGEMS_VERSION}  (commit $(git -C "$src" rev-parse --short=9 HEAD))"
# Scoped to the flag_gems dist so it can only ever override this project.
export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_FLAG_GEMS="$FLAGGEMS_VERSION"
echo ">>> daily version: $SETUPTOOLS_SCM_PRETEND_VERSION_FOR_FLAG_GEMS"

echo ">>> building pure-Python wheel"
mkdir -p "$OUTDIR"
# Build in an isolated venv: on Ubuntu 24.04 (Python 3.12) the system
# interpreter is PEP 668 externally-managed and pip refuses to run against it.
python3 -m venv "$workdir/venv"
"$workdir/venv/bin/pip" wheel "$src" --no-deps -w "$OUTDIR"

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
