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

# 6 FlagOS operator libraries (纯 Python) — builds each as a py3-none-any wheel
# from its upstream release tag.
#
# This is the packaging companion to .github/workflows/flaglibs-wheel.yml.
# EVERY build runs in CI (GitHub Actions); it is not meant to be run on a
# workstation.  The wheel is platform-independent (no vendor toolchain), so
# this is a plain venv script, not a container build — the same shape as
# packaging/flaggems/build.sh.
#
# Version source (see docs/decisions.md): each wheel is versioned by its own
# upstream tag — pyproject static version for most, setuptools_scm (git tags)
# for flag_attn. We build exactly the tag, so the wheel carries the release
# version (`v0.3.0` -> `0.3.0`). No build-infra-synthesized version number.
#
# Selection:   FLAGLIBS="flag_attn flagsparse"   (default: all six)
# Output:      OUTDIR=/tmp/wheels                 (default: ./wheels)
# Ref override: REF_flag_attn=v0.4.0 per lib       (default: build-config.yaml)
#
# Output: $OUTDIR/<pkg>-<version>-py3-none-any.whl per library.
set -euo pipefail

_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$_here/build-config.yaml"

FLAGLIBS="${FLAGLIBS:-}"
OUTDIR="${OUTDIR:-$(pwd)/wheels}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# All pip/python work goes through an isolated venv (PEP 668 on Ubuntu 24.04).
python3 -m venv "$workdir/venv"
py="$workdir/venv/bin/python"

# Parse build-config.yaml with a tiny python read (the venv interpreter already
# has PyYAML via pip below only if needed; fall back to a naive YAML subset here
# so the script does not need a dependency beyond stdlib). We emit one
# space-separated line per lib: "<key> <repo> <default_ref> <kind>". None of the
# four fields contain a space, so `set --` parses them portably (no awk/tab
# tricks — macOS BSD awk treats -F'\t' as a literal backslash-t).
lib_specs="$(
  "$py" - <<PYEOF
try:
    import yaml
except ImportError:
    # PyYAML not in the venv; parse the flat subset ourselves. build-config.yaml
    # is a key->inline-map sequence with no nested collections, so this is safe.
    yaml = None
if yaml is not None:
    with open(r"$_here/build-config.yaml") as f:
        cfg = yaml.safe_load(f)
    for key, m in cfg.items():
        print(f"{key} {m['repo']} {m['default_ref']} {'scm' if m.get('scm') else 'static'}")
else:
    import re
    key, vals = None, {}
    for line in open(r"$_here/build-config.yaml"):
        line = line.rstrip("\n")
        if not line or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\S+):\s*$", line)
        if m:
            if vals:
                print(f"{key} {vals['repo']} {vals['default_ref']} {vals.get('scm','static')}")
            key, vals = m.group(1), {}
            continue
        km = re.match(r"^\s+(\S+):\s*(.*)$", line)
        if km and key:
            v = km.group(2).strip()
            vals[km.group(1).strip()] = v
        else:
            # Inline map: `flag_attn:      {repo: FlagAttention, ...}`
            im = re.match(r"^(\S+):\s*\{(.*)\}\s*$", line)
            if im and not key:
                k, inner = im.group(1), im.group(2)
                for kv in inner.split(","):
                    kk, _, vv = kv.strip().partition(":")
                    vals[kk.strip()] = vv.strip()
                print(f"{k} {vals['repo']} {vals['default_ref']} {vals.get('scm','static')}")
                key, vals = k, {}
    if vals:
        print(f"{key} {vals['repo']} {vals['default_ref']} {vals.get('scm','static')}")
PYEOF
)"

# Resolve the selected lib list: default = all keys in build-config.yaml.
if [ -z "$FLAGLIBS" ]; then
  FLAGLIBS="$(printf '%s\n' "$lib_specs" | cut -d' ' -f1 | tr '\n' ' ')"
fi

mkdir -p "$OUTDIR"
echo ">>> building: $FLAGLIBS"
echo ">>> output: $OUTDIR"
echo

# setuptools_scm is needed only for the flag_attn (scm-versioned) build; install
# once up front, harmless for the rest.
"$py" -m pip install --quiet "setuptools-scm>=8,<10"

for key in $FLAGLIBS; do
  spec="$(printf '%s\n' "$lib_specs" | grep -F "$key " | head -1)"
  set -- $spec
  repo="$2"
  default_ref="$3"
  kind="$4"
  [ -n "$kind" ] || kind=static

  # Per-lib ref override, e.g. REF_flag_attn=v0.4.0. Key uses '_' in the env
  # name (flagfft-codegen -> REF_flagfft_codegen).
  envkey="REF_${key//-/_}"
  ref="${!envkey:-$default_ref}"

  echo ">>> flaglibs: $key @ $ref ($kind)"
  src="$workdir/$key"
  repo_url="https://github.com/flagos-ai/$repo.git"
  if [ "$kind" = "scm" ]; then
    # setuptools_scm reads git tags: needs the full history, not a shallow
    # branch. Checkout the ref after fetching all tags (same as flaggems).
    git clone --quiet "$repo_url" "$src"
    git -C "$src" fetch --quiet --tags --force origin || true
    git -C "$src" checkout --quiet "$ref"
  else
    # Static version in pyproject: a shallow tag checkout is enough.
    git clone --quiet --depth 1 --branch "$ref" "$repo_url" "$src"
  fi

  echo "   version: $(cd "$src" && git describe --tags 2>/dev/null || echo "$ref")"
  "$py" -m pip wheel "$src" --no-deps --no-build-isolation -w "$OUTDIR"

  # Exactly one wheel for this lib, and it must be py3-none-any. A platform tag
  # means the build accidentally compiled C++ (wrong ref) — fail loudly.
  wheel="$(ls -t "$OUTDIR"/"${key//-/_}"-*.whl 2>/dev/null | head -1)"
  if [ -z "$wheel" ]; then
    echo "ERROR: no ${pkg} wheel produced" >&2
    exit 1
  fi
  case "$wheel" in
    *-py3-none-any.whl) : ;;
    *) echo "ERROR: expected py3-none-any, got $(basename "$wheel") (C++ backend?)" >&2
       exit 1 ;;
  esac
  echo ">>> built: $(basename "$wheel")"
  echo
done

echo ">>> all wheels:"
ls -1 "$OUTDIR"/*.whl