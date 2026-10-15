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
# install.sh — one-click installer for the FlagOS runtime + app layer.
#
# TEMPLATE: the placeholder tokens are filled by scripts/build_bundle.py at
# bundle build time; the shipped install.sh has none left. Every package is
# installed from the sibling wheelhouse/ with `pip install --no-index
# --find-links`, so the install never needs a network.
#
#   sudo ./install.sh --prefix /opt/flagos --app-version 0.24.0
#
# One bundle carries every version in the app's app-versions.yaml;
# --app-version selects which requirements-<version>.txt to install.
# ============================================================================

set -euo pipefail

# ── Metadata (substituted at build time) ────────────────────────────────────
APP="@APP@"
VENDOR="@VENDOR@"
BACKEND="@BACKEND@"
VERSION="@VERSION@"
PYTHON_VERSION="@PYTHON_VERSION@"
CPYTHON_TARBALL="@CPYTHON_TARBALL@"
FLAGTREE_PIN="@FLAGTREE_PIN@"             # "flagtree==0.7.0" or ""
TRITON_PIN="@TRITON_PIN@"                 # "triton==3.6.0" or ""
TRITON_EXTRA="@TRITON_EXTRA@"             # space-separated overlay wheels or ""
APP_ENV="@APP_ENV@"                       # raw "KEY=value" lines (may be empty)
RUNTIME_ENV="@RUNTIME_ENV@"               # raw "KEY=value" lines (may be empty)
SDK_NOTE="@SDK_NOTE@"                     # host prerequisite, printed on smoke failure
LAUNCHER="@LAUNCHER@"                     # bin/<launcher> name (e.g. vllm-serve)
ENTRYPOINT="@ENTRYPOINT@"                 # module the launcher execs, or "" (none)
SMOKE_IMPORTS="@SMOKE_IMPORTS@"           # "import a; import b" or ""

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEELHOUSE="$SELF_DIR/wheelhouse"
PYTHON_DIR="$SELF_DIR/python"

PREFIX="${FLAGOS_PREFIX:-/opt/flagos}"
APP_VERSION=""

usage() {
    cat <<EOF
Usage: $0 --app-version <ver> [--prefix <dir>]

Install the FlagOS runtime + ${APP} Python layer into <dir>
(default /opt/flagos). Bundled ${APP} versions are listed in the sibling
requirements-<ver>.txt files.

  --prefix <dir>         install prefix (default /opt/flagos)
  --app-version <ver>    which bundled ${APP} version to install (required)
  -h, --help             this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix)
            [ $# -ge 2 ] || { echo "error: --prefix needs a value" >&2; exit 2; }
            PREFIX="$2"; shift 2 ;;
        --app-version)
            [ $# -ge 2 ] || { echo "error: --app-version needs a value" >&2; exit 2; }
            APP_VERSION="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -z "$APP_VERSION" ]; then
    echo "error: --app-version is required (bundled: $(ls "$SELF_DIR"/requirements-*.txt 2>/dev/null | sed -n 's/.*requirements-\(.*\)\.txt/\1/p' | tr '\n' ' '))" >&2
    exit 2
fi

REQ_DELTA="$SELF_DIR/requirements-$APP_VERSION.txt"
if [ ! -r "$REQ_DELTA" ]; then
    echo "error: ${APP} version '$APP_VERSION' is not bundled." >&2
    echo "  bundled: $(ls "$SELF_DIR"/requirements-*.txt 2>/dev/null | sed -n 's/.*requirements-\(.*\)\.txt/\1/p' | tr '\n' ' ')" >&2
    exit 2
fi

if [ "$(id -u)" -ne 0 ] && [ ! -w "$(dirname "$PREFIX")" ]; then
    echo "error: cannot write under $(dirname "$PREFIX") — re-run with sudo or a writable --prefix" >&2
    exit 2
fi

echo "==> installing FlagOS ${APP} ${VERSION} (backend ${VENDOR}-${BACKEND})"
echo "    prefix: ${PREFIX}   ${APP} version: ${APP_VERSION}"

# ── 1. Hermetic CPython + venv ──────────────────────────────────────────────
# The standalone CPython lands in ~/.local/share/uv/python/ — the exact path
# the runtime image uses, because `uv venv --relocatable` symlinks the venv's
# interpreter back to it. A bare-metal install and the image share one layout.
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

# uv needs no pip to install pip; --no-index keeps the seed local.
"$PYTHON_DIR/uv" pip install --python "$PREFIX/bin/python" \
    --no-index --find-links "$WHEELHOUSE" pip setuptools wheel

"$PREFIX/bin/python" -c "import sys; assert sys.version_info[:2] == tuple(int(x) for x in '${PYTHON_VERSION}'.split('.')[:2])" \
    || { echo "error: venv python does not match ${PYTHON_VERSION}" >&2; exit 1; }

# ── 2. Runtime closure + selected app delta ─────────────────────────────────
echo "==> installing runtime layer + ${APP} ${APP_VERSION} (--no-index)"
"$PREFIX/bin/pip" install --no-index --find-links "$WHEELHOUSE" \
    -r "$SELF_DIR/requirements.txt" \
    -r "$REQ_DELTA"

# ── 3. Compilers to their side dirs ────────────────────────────────────────
# Compilers live OUT of site-packages in $PREFIX/<compiler>; the `compiler`
# shim toggles them via PYTHONPATH. (Candidate layout — the image still uses
# /opt/flagtree, /opt/triton; if this proves cleaner, the image can follow.)
# The vendor triton overlay wheels ship a full triton tree and must be unzipped
# OVER the side dir — `pip install --target` cannot extend an existing
# top-level triton/ dir.
if [ -n "$FLAGTREE_PIN" ]; then
    echo "==> installing FlagTree to ${PREFIX}/flagtree"
    mkdir -p "$PREFIX/flagtree"
    "$PREFIX/bin/pip" install --no-index --find-links "$WHEELHOUSE" \
        --target "$PREFIX/flagtree" "$FLAGTREE_PIN"
fi

if [ -n "$TRITON_PIN" ]; then
    echo "==> installing Triton to ${PREFIX}/triton"
    mkdir -p "$PREFIX/triton"
    "$PREFIX/bin/pip" install --no-index --find-links "$WHEELHOUSE" \
        --target "$PREFIX/triton" "$TRITON_PIN"
    if [ -n "$TRITON_EXTRA" ]; then
        for spec in $TRITON_EXTRA; do
            echo "==> overlaying ${spec} onto ${PREFIX}/triton"
            _tmp="$(mktemp -d)"
            "$PREFIX/bin/pip" download --no-index --find-links "$WHEELHOUSE" \
                --no-deps -d "$_tmp" "$spec" >/dev/null
            (cd "$PREFIX/triton" && unzip -qo "$_tmp"/*.whl)
            rm -rf "$_tmp"
        done
    fi
fi

# ── 4. Vendor env, compiler shim, launcher ─────────────────────────────────
mkdir -p "$PREFIX/etc/profile.d" "$PREFIX/bin" "$PREFIX/etc/flagos"

# 'export'-prefixed so the vars survive an exec (a bare KEY=value assignment
# dies with the sourcing shell).
printf '%s\n' "$RUNTIME_ENV" | sed '/^$/d; s/^/export /' > "$PREFIX/etc/profile.d/runtime_env.sh"
printf '%s\n' "$APP_ENV"     | sed '/^$/d; s/^/export /' > "$PREFIX/etc/profile.d/app_env.sh"

# zz-compiler.sh — the compiler switcher, the same shape runtime/zz-compiler.sh
# bakes into every runtime image, re-rooted at $PREFIX. zz- sorts last so its
# PYTHONPATH export wins over any vendor env file.
cat > "$PREFIX/etc/profile.d/zz-compiler.sh" <<EOF
# Generated by install.sh — do not edit. Mirrors runtime/zz-compiler.sh.
_compiler_side_dirs="${PREFIX}/flagtree ${PREFIX}/triton"
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
            [ -d "${PREFIX}/flagtree/triton" ] || { echo "flagtree: not available on this backend" >&2; return 1; }
            dir="${PREFIX}/flagtree" ;;
        triton)
            [ -d "${PREFIX}/triton/triton" ] || { echo "triton: not available on this backend" >&2; return 1; }
            dir="${PREFIX}/triton" ;;
        ""|status|help)
            echo "available compilers:"
            [ -d "${PREFIX}/flagtree/triton" ] && echo "  flagtree  (default)"
            [ -d "${PREFIX}/triton/triton" ] && echo "  triton"
            if ! _compiler_active_dir >/dev/null; then
                if [ -d "${PREFIX}/flagtree/triton" ]; then dir="${PREFIX}/flagtree"
                elif [ -d "${PREFIX}/triton/triton" ]; then dir="${PREFIX}/triton"; fi
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
    if [ -d "${PREFIX}/flagtree/triton" ]; then
        export PYTHONPATH="${PREFIX}/flagtree\${PYTHONPATH:+:}\${PYTHONPATH:-}"
    elif [ -d "${PREFIX}/triton/triton" ]; then
        export PYTHONPATH="${PREFIX}/triton\${PYTHONPATH:+:}\${PYTHONPATH:-}"
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

# Launcher — sources the profile.d env, then execs the app entry, mirroring
# app/<app>/<launcher> for a bare-metal prefix.
if [ -n "$ENTRYPOINT" ]; then
    cat > "$PREFIX/bin/$LAUNCHER" <<EOF
#!/bin/bash
set -euo pipefail
for f in "${PREFIX}"/etc/profile.d/*.sh; do [ -r "\$f" ] && . "\$f"; done
exec "${PREFIX}/bin/python" -m ${ENTRYPOINT} "\$@"
EOF
    chmod +x "$PREFIX/bin/$LAUNCHER"
fi

# ── 5. Smoke test ───────────────────────────────────────────────────────────
if [ -n "$SMOKE_IMPORTS" ]; then
    echo "==> smoke test (${SMOKE_IMPORTS})"
    . "$PREFIX/etc/profile.d/zz-compiler.sh"
    if ! "$PREFIX/bin/python" -c \
        "${SMOKE_IMPORTS}" 2> "$SELF_DIR/smoke.err"; then
        echo "error: import smoke test failed — the preinstalled SDK/driver may be missing or mismatched." >&2
        echo "  backend requirement: ${SDK_NOTE}" >&2
        sed 's/^/  | /' "$SELF_DIR/smoke.err" >&2
        exit 1
    fi
    rm -f "$SELF_DIR/smoke.err"
fi

cat <<EOF

Done. FlagOS ${APP} ${VERSION} installed to ${PREFIX}.

To use it in a shell:
    source ${PREFIX}/etc/profile.d/zz-compiler.sh   # compiler + PYTHONPATH
    source ${PREFIX}/etc/profile.d/runtime_env.sh
    source ${PREFIX}/etc/profile.d/app_env.sh
EOF

if [ -n "$ENTRYPOINT" ]; then
    cat <<EOF

Serve:
    ${PREFIX}/bin/${LAUNCHER} --help
EOF
fi

cat <<EOF

Switch compiler:  ${PREFIX}/bin/compiler flagtree|triton
EOF
