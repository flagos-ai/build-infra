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

# Build the pure-Python flaggems_vllm wheel from FlagGems-vllm source.
#
# The wheel is platform-independent (py3-none-any): no vendor toolchain, so
# this is a plain venv script, not a container build — the same shape as
# packaging/flaggems/build.sh.
#
# VERSION: FlagGems-vllm carries a STATIC version in pyproject.toml and has no
# setuptools_scm, so where flaggems asks git for the version this one reads the
# static string. The two cases are the same two:
#
#   * HEAD is on a tag (a release): the TAG is the version (packaging/flaglibs
#     docs/decisions.md D4: a tag and a pyproject string that disagree resolve
#     in the tag's favour). A disagreement is reported rather than hidden, and
#     the wheel is renamed to match — the static string is rewritten in the
#     clone, so a build is never published under a version no file names.
#   * HEAD is past the last tag (the daily, off main): the dev suffix becomes a
#     UTC date on the same base, 0.3.0-dev1 -> 0.3.0.dev20261104. The base is
#     upstream's; nothing is invented here.
#
# Either way the rewrite lands in the throwaway clone only, never upstream.
#
# Uploading is the workflow's job; this only builds. Output: $OUTDIR/*.whl.
#
#   FLAGGEMS_VLLM_REF=<ref> ./build.sh                     # build from a ref
#   OUTDIR=/tmp/wheels ./build.sh                          # choose output dir
#   FLAGGEMS_VLLM_REPO=/path/to/FlagGems-vllm ./build.sh   # local clone
set -euo pipefail

REPO="${FLAGGEMS_VLLM_REPO:-https://github.com/flagos-ai/FlagGems-vllm.git}"
REF="${FLAGGEMS_VLLM_REF:-main}"
OUTDIR="${OUTDIR:-$(pwd)/wheels}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
src="$workdir/FlagGems-vllm"

# All pip/python work goes through an isolated venv: on Ubuntu 24.04 (Python
# 3.12) the system interpreter is PEP 668 externally-managed and pip refuses to
# run against it. The venv lives in the throwaway workdir and dies with it.
python3 -m venv "$workdir/venv"
py="$workdir/venv/bin/python"
"$py" -m pip install --quiet packaging

echo ">>> cloning FlagGems-vllm @ ${REF} (with tags)"
git clone --quiet "$REPO" "$src"
git -C "$src" fetch --quiet --tags --force origin || true
git -C "$src" checkout --quiet "$REF"

version="$("$py" - "$src" <<'PY'
import datetime, pathlib, re, subprocess, sys

from packaging.version import Version

path = pathlib.Path(sys.argv[1]) / "pyproject.toml"
text = path.read_text()
m = re.search(r'(?m)^version\s*=\s*"(.*)"\s*$', text)
if not m:
    sys.exit("ERROR: no static version in pyproject.toml — the version rule needs one")
static = m.group(1)

def rewrite(version):
    """Point pyproject.toml at `version`, in this clone only."""
    # The regex must land on [project].version: `[tool.*]` sections carry
    # `version = ` lines too, and one of those would build the wrong value
    # silently. count=1 plus the read-back is that guard.
    new, hits = re.subn(
        r'(?m)^version\s*=\s*".*"\s*$', f'version = "{version}"', text, count=1
    )
    if hits != 1:
        sys.exit('ERROR: no static `version = "..."` line to rewrite')
    path.write_text(new)
    back = re.search(r'(?m)^version\s*=\s*"(.*)"\s*$', new)
    if not back or back.group(1) != version:
        sys.exit(f"ERROR: pyproject version is not {version!r} after the rewrite")

tag = subprocess.run(
    ["git", "-C", str(path.parent), "describe", "--tags", "--exact-match"],
    capture_output=True, text=True,
).stdout.strip()
if tag:
    version = str(Version(tag.lstrip("v")))
    # A tag and the string disagreeing is upstream's to fix, not this build's
    # to paper over — but it decides what the wheel is named, so it is said
    # out loud rather than resolved silently.
    if Version(static) != Version(version):
        print(f">>> WARNING: tag {tag} declares {static} in pyproject; "
              f"shipping {version} (the tag wins, flaglibs D4)", file=sys.stderr)
    if static != version:
        rewrite(version)
else:
    # `0.3.0-dev1` -> `0.3.0`, then the UTC date. Upstream spells its
    # development line `X.Y.0-devN`, so the dev suffix is all that has to go; a
    # local segment goes with it, since a dev build cannot carry one.
    base = re.sub(r"\+.*$", "", static)
    base = re.sub(r"[-.]?dev\d*$", "", base, flags=re.IGNORECASE)
    version = f"{base}.dev{datetime.datetime.now(datetime.timezone.utc):%Y%m%d}"
    rewrite(version)

if str(Version(version)) != version:
    sys.exit(f"ERROR: version {version!r} is not PEP 440 normal form")
print(version)
PY
)"

echo ">>> version: ${version}  (commit $(git -C "$src" rev-parse --short=9 HEAD))"

echo ">>> building pure-Python wheel"
mkdir -p "$OUTDIR"
"$py" -m pip wheel "$src" --no-deps -w "$OUTDIR"

wheel="$(ls -t "$OUTDIR"/flaggems_vllm-*.whl 2>/dev/null | head -1)"
if [ -z "$wheel" ]; then
  echo "ERROR: no flaggems_vllm wheel produced" >&2
  exit 1
fi
# The pure-Python wheel must be py3-none-any at exactly the version above. A
# platform tag means the build hit a C++ backend (wrong ref); a different
# version means the version rule missed the field the build backend reads —
# both are silent-publish hazards, so both fail here.
case "$(basename "$wheel")" in
  "flaggems_vllm-${version}-py3-none-any.whl") : ;;
  *) echo "ERROR: expected flaggems_vllm-${version}-py3-none-any.whl, got" \
          "$(basename "$wheel")" >&2
     exit 1 ;;
esac

# The per-backend tune configs ship as package data
# (`[tool.setuptools.package-data]`): a wheel that loses them still imports and
# then finds no configs on a node, so the shipped set is compared against the
# source tree here rather than discovered during a verification run. It is a
# comparison and not a threshold because the count is a property of the ref —
# v0.1.0 legitimately carries four.
"$py" - "$wheel" "$src/src" <<'PY'
import pathlib, sys, zipfile

wheel, tree = sys.argv[1], pathlib.Path(sys.argv[2])
in_tree = {p.relative_to(tree).as_posix() for p in tree.rglob("*.yaml")}
with zipfile.ZipFile(wheel) as zf:
    in_wheel = {n for n in zf.namelist() if n.endswith(".yaml")}
missing = sorted(in_tree - in_wheel)
if not in_tree:
    sys.exit("ERROR: no yaml under src/ — wrong tree, or package-data is not the mechanism")
if missing:
    sys.exit(f"ERROR: {len(missing)} yaml file(s) in src/ are not in the wheel — "
             f"package-data did not apply: {missing[:3]}")
print(f">>> package data: {len(in_wheel)} yaml files, all {len(in_tree)} from src/")
PY

echo ">>> built: $(basename "$wheel")"
