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

# ============================================================================
# install.sh — offline one-click installer for the FlagOS runtime + app layer.
#
# TEMPLATE: this file is a template filled by scripts/build_offline_bundle.py.
# The @PLACEHOLDER@ tokens are substituted at bundle build time; the shipped
# install.sh has none left. It is the ONLY entry point of the bundle and never
# touches the network — every package is installed from the sibling wheelhouse/
# with `pip install --no-index --find-links`.
#
#   sudo ./install.sh --prefix /opt/flagos --vllm-version 0.24.0
#
# The same bundle installs any bundled app version; --vllm-version selects
# which requirements-<version>.txt the install consumes. One install installs
# exactly one version.
# ============================================================================

set -euo pipefail

# ── Metadata (substituted at build time) ────────────────────────────────────
APP="@APP@"
VENDOR="@VENDOR@"
BACKEND="@BACKEND@"
VERSION="@VERSION@"
PYTHON_VERSION="@PYTHON_VERSION@"
CPYTHON_TARBALL="@CPYTHON_TARBALL@"
DEFAULT_COMPILER="@DEFAULT_COMPILER@"     # flagtree | triton | none
FLAGTREE_PIN="@FLAGTREE_PIN@"             # "flagtree==0.7.0" or ""
TRITON_PIN="@TRITON_PIN@"                 # "triton==3.6.0" or ""
TRITON_EXTRA="@TRITON_EXTRA@"             # space-separated overlay wheels or ""
APP_ENV="@APP_ENV@"                       # raw "KEY=value" lines (may be empty)
RUNTIME_ENV="@RUNTIME_ENV@"               # raw "KEY=value" lines (may be empty)
SDK_NOTE="@SDK_NOTE@"                     # human note printed on smoke-test failure

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEELHOUSE="$SELF_DIR/wheelhouse"
PYTHON_DIR="$SELF_DIR/python"

PREFIX="${FLAGOS_PREFIX:-/opt/flagos}"
VLLM_VERSION=""

usage() {
    cat <<EOF
Usage: $0 --vllm-version <ver> [--prefix <dir>]

Install the FlagOS runtime + ${APP} Python layer OFFLINE into <dir>
(default /opt/flagos). ${APP} versions bundled: see the sibling
requirements-<ver>.txt files.

  --prefix <dir>         install prefix (default /opt/flagos)
  --vllm-version <ver>   which bundled ${APP} version to install (required)
  -h, --help             this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix)
            [ $# -ge 2 ] || { echo "error: --prefix needs a value" >&2; exit 2; }
            PREFIX="$2"; shift 2 ;;
        --vllm-version)
            [ $# -ge 2 ] || { echo "error: --vllm-version needs a value" >&2; exit 2; }
            VLLM_VERSION="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -z "$VLLM_VERSION" ]; then
    echo "error: --vllm-version is required (bundled: $(ls "$SELF_DIR"/requirements-*.txt 2>/dev/null | sed -n 's/.*requirements-\(.*\)\.txt/\1/p' | tr '\n' ' '))" >&2
    exit 2
fi

REQ_DELTA="$SELF_DIR/requirements-$VLLM_VERSION.txt"
if [ ! -r "$REQ_DELTA" ]; then
    echo "error: ${APP} version '$VLLM_VERSION' is not bundled." >&2
    echo "  bundled: $(ls "$SELF_DIR"/requirements-*.txt 2>/dev/null | sed -n 's/.*requirements-\(.*\)\.txt/\1/p' | tr '\n' ' ')" >&2
    exit 2
fi

if [ "$(id -u)" -ne 0 ] && [ ! -w "$(dirname "$PREFIX")" ]; then
    echo "error: cannot write under $(dirname "$PREFIX") — re-run with sudo or a writable --prefix" >&2
    exit 2
fi

echo "==> installing FlagOS ${APP} ${VERSION} (backend ${VENDOR}-${BACKEND})"
echo "    prefix: ${PREFIX}   ${APP} version: ${VLLM_VERSION}   (offline)"

# ── 1. Hermetic CPython + venv ──────────────────────────────────────────────
# The bundle ships the uv-managed standalone CPython for the backend's Python
# version and a relocatable uv. No host Python is required or touched. The
# standalone tree lands in ~/.local/share/uv/python/ — the exact path the
# runtime image uses (uv venv --relocatable symlinks the venv's interpreter
# back to it), so a bare-metal install and the image share one layout.
mkdir -p "$PREFIX"
echo "==> extracting standalone CPython ${PYTHON_VERSION}"
mkdir -p "$HOME/.local/share/uv/python"
tar xzf "$PYTHON_DIR/$CPYTHON_TARBALL" -C "$HOME/.local/share/uv/python"
PY_BIN="$(find "$HOME/.local/share/uv/python" -maxdepth 3 \( -type f -o -type l \) -path '*/bin/python3' | head -n1)"
if [ -z "$PY_BIN" ]; then
    echo "error: standalone CPython not found after extraction" >&2
    exit 1
fi

echo "==> creating venv at ${PREFIX}"
"$PYTHON_DIR/uv" venv "$PREFIX" --python "$PY_BIN" --relocatable

# Seed pip/setuptools/wheel from the wheelhouse via uv (uv needs no pip to
# install pip, and --no-index keeps the seed offline) so the rest of the
# install runs the same `pip` the images use.
"$PYTHON_DIR/uv" pip install --python "$PREFIX/bin/python" \
    --no-index --find-links "$WHEELHOUSE" pip setuptools wheel

"$PREFIX/bin/python" -c "import sys; assert sys.version_info[:2] == tuple(int(x) for x in '${PYTHON_VERSION}'.split('.')[:2])" \
    || { echo "error: venv python does not match ${PYTHON_VERSION}" >&2; exit 1; }

# ── 2. Runtime closure + selected app delta ─────────────────────────────────
echo "==> installing runtime layer + ${APP} ${VLLM_VERSION} (--no-index)"
"$PREFIX/bin/pip" install --no-index --find-links "$WHEELHOUSE" \
    -r "$SELF_DIR/requirements.txt" \
    -r "$REQ_DELTA"

# ── 3. Compilers to their side dirs (mirror the runtime image layout) ──────
# Compilers live OUT of site-packages in $PREFIX/opt/<compiler>; the `compiler`
# shim toggles them via PYTHONPATH. Installed WITH deps, exactly as the
# runtime Containerfile installs them (flagtree bundles triton/; the vendor
# triton side dir carries triton-*.dist-info so a bare `triton` dep resolves).
if [ -n "$FLAGTREE_PIN" ]; then
    echo "==> installing FlagTree to ${PREFIX}/opt/flagtree"
    mkdir -p "$PREFIX/opt/flagtree"
    "$PREFIX/bin/pip" install --no-index --find-links "$WHEELHOUSE" \
        --target "$PREFIX/opt/flagtree" "$FLAGTREE_PIN"
fi

if [ -n "$TRITON_PIN" ]; then
    echo "==> installing Triton to ${PREFIX}/opt/triton"
    mkdir -p "$PREFIX/opt/triton"
    "$PREFIX/bin/pip" install --no-index --find-links "$WHEELHOUSE" \
        --target "$PREFIX/opt/triton" "$TRITON_PIN"
    # Backend overlay wheels (triton_ascend, triton-gcu, ...) ship a full
    # triton tree and must be unzipped OVER the side dir — `pip install
    # --target` cannot extend an existing top-level triton/ dir (same rule the
    # runtime Containerfile follows).
    if [ -n "$TRITON_EXTRA" ]; then
        for spec in $TRITON_EXTRA; do
            echo "==> overlaying ${spec} onto ${PREFIX}/opt/triton"
            _tmp="$(mktemp -d)"
            "$PREFIX/bin/pip" download --no-index --find-links "$WHEELHOUSE" \
                --no-deps -d "$_tmp" "$spec" >/dev/null
            (cd "$PREFIX/opt/triton" && unzip -qo "$_tmp"/*.whl)
            rm -rf "$_tmp"
        done
    fi
fi

# ── 4. Vendor env, compiler shim, launcher ─────────────────────────────────
mkdir -p "$PREFIX/etc/profile.d" "$PREFIX/bin" "$PREFIX/etc/flagos"

# runtime_env.sh / app_env.sh — 'export'-prefixed so the vars survive an exec
# (a bare KEY=value assignment dies with the sourcing shell).
printf '%s\n' "$RUNTIME_ENV" | sed '/^$/d; s/^/export /' > "$PREFIX/etc/profile.d/runtime_env.sh"
printf '%s\n' "$APP_ENV"     | sed '/^$/d; s/^/export /' > "$PREFIX/etc/profile.d/app_env.sh"

# zz-compiler.sh — the compiler switcher, adapted from runtime/zz-compiler.sh
# for a $PREFIX tree. zz- sorts last so its PYTHONPATH export wins over any
# vendor env file.
cat > "$PREFIX/etc/profile.d/zz-compiler.sh" <<EOF
# Generated by install.sh — do not edit. See runtime/zz-compiler.sh upstream.
_compiler_side_dirs="${PREFIX}/opt/flagtree ${PREFIX}/opt/triton"
_compiler_active_dir() {
    for d in \$_compiler_side_dirs; do
        case ":\${PYTHONPATH:-}:" in
            *":\${d}:"*) echo "\$d"; return 0 ;;
        esac
    done
    return 1
}
_compiler_strip_side_dirs() {
    local cleaned=""
    IFS=":"
    for p in \${PYTHONPATH:-}; do
        case " \$_compiler_side_dirs " in
            *" \$p "*) ;;
            *) [ -n "\$cleaned" ] && cleaned="\${cleaned}:\${p}" || cleaned="\$p" ;;
        esac
    done
    printf '%s' "\$cleaned"
}
compiler() {
    local dir=""
    case "\${1:-}" in
        flagtree)
            [ -d "${PREFIX}/opt/flagtree/triton" ] || { echo "flagtree: not available on this backend" >&2; return 1; }
            dir="${PREFIX}/opt/flagtree" ;;
        triton)
            [ -d "${PREFIX}/opt/triton/triton" ] || { echo "triton: not available on this backend" >&2; return 1; }
            dir="${PREFIX}/opt/triton" ;;
        ""|status|help)
            echo "available compilers:"
            [ -d "${PREFIX}/opt/flagtree/triton" ] && echo "  flagtree  (default)"
            [ -d "${PREFIX}/opt/triton/triton" ] && echo "  triton"
            if ! _compiler_active_dir >/dev/null; then
                if [ -d "${PREFIX}/opt/flagtree/triton" ]; then dir="${PREFIX}/opt/flagtree"
                elif [ -d "${PREFIX}/opt/triton/triton" ]; then dir="${PREFIX}/opt/triton"; fi
            fi
            ;;
        *) echo "Usage: compiler [flagtree|triton]" >&2; return 1 ;;
    esac
    if [ -n "\$dir" ]; then
        local cleaned
        cleaned=\$(_compiler_strip_side_dirs)
        if [ -n "\$cleaned" ]; then export PYTHONPATH="\${dir}:\${cleaned}"
        else export PYTHONPATH="\${dir}"; fi
        echo "\$(basename "\$dir") (active)"
    else
        echo "active compiler:"
        _compiler_active_dir || echo "  (no compiler side dir on PYTHONPATH)"
    fi
}
# Default compiler active in every shell.
if ! _compiler_active_dir >/dev/null; then
    if [ -d "${PREFIX}/opt/flagtree/triton" ]; then
        export PYTHONPATH="${PREFIX}/opt/flagtree\${PYTHONPATH:+:}\${PYTHONPATH:-}"
    elif [ -d "${PREFIX}/opt/triton/triton" ]; then
        export PYTHONPATH="${PREFIX}/opt/triton\${PYTHONPATH:+:}\${PYTHONPATH:-}"
    fi
fi
EOF

# compiler shim — `compiler` in $PREFIX/bin, for shells that don't source
# profile.d (non-login, non-interactive).
cat > "$PREFIX/bin/compiler" <<EOF
#!/bin/bash
. "${PREFIX}/etc/profile.d/zz-compiler.sh"
compiler "\$@"
EOF
chmod +x "$PREFIX/bin/compiler"

# vllm-serve — the single serve command, mirroring app/vllm/vllm-serve for a
# bare-metal prefix: source the profile.d env, then exec the API server.
cat > "$PREFIX/bin/vllm-serve" <<EOF
#!/bin/bash
set -euo pipefail
for f in "${PREFIX}"/etc/profile.d/*.sh; do [ -r "\$f" ] && . "\$f"; done
exec "${PREFIX}/bin/python" -m vllm.entrypoints.openai.api_server "\$@"
EOF
chmod +x "$PREFIX/bin/vllm-serve"

# ── 5. Smoke test ───────────────────────────────────────────────────────────
echo "==> smoke test (import torch, flag_gems, triton, vllm, vllm_fl)"
. "$PREFIX/etc/profile.d/zz-compiler.sh"
if ! "$PREFIX/bin/python" -c \
    "import torch; import flag_gems; import triton; import vllm; import vllm_fl" 2> "$SELF_DIR/smoke.err"; then
    echo "error: import smoke test failed — the preinstalled SDK/driver may be missing or mismatched." >&2
    echo "  backend requirement: ${SDK_NOTE}" >&2
    sed 's/^/  | /' "$SELF_DIR/smoke.err" >&2
    exit 1
fi
rm -f "$SELF_DIR/smoke.err"

cat <<EOF

Done. FlagOS ${APP} ${VLLM_VERSION} installed offline to ${PREFIX}.

To use it in a shell:
    source ${PREFIX}/etc/profile.d/zz-compiler.sh   # compiler + PYTHONPATH
    source ${PREFIX}/etc/profile.d/runtime_env.sh
    source ${PREFIX}/etc/profile.d/app_env.sh

Serve:
    ${PREFIX}/bin/vllm-serve --model <path> --port 8031

Switch compiler:  ${PREFIX}/bin/compiler flagtree|triton
EOF
