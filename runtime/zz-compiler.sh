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
# zz-compiler.sh — runtime compiler switcher, baked into every runtime image.
#
# The zz- prefix forces this to sort LAST in /etc/profile.d/*.sh (sourced
# alphabetically). It must run after any vendor.sh that exports PYTHONPATH
# absolutely (ascend's set_env.sh capture does), otherwise that vendor.sh
# clobbers the compiler side dir off PYTHONPATH and triton stops importing.
#
# FlagTree (default, when present) lives in /opt/flagtree and the vendor
# Triton lives in /opt/triton.  Neither is in site-packages, so their
# dist-infos (and the entry points inside them) are only visible to
# importlib.metadata when that compiler's dir is on PYTHONPATH.  This file
# is sourced from /etc/profile.d so the default compiler is active in every
# shell (login, non-login interactive, and bash -c via BASH_ENV), and
# 'compiler <name>' toggles between the two.
#
#   compiler                 — show what's available and what's active
#   compiler flagtree        — switch to FlagTree (default when present)
#   compiler triton          — switch to the vendor Triton
#   compiler flagtree <ver>  — install that FlagTree version, then switch to it
#
# FlagTree releases on its own cadence, and a bump would otherwise mean
# rebuilding every image above the runtime. So a different version can also be
# requested at container start, before any launcher exec's:
#
#   docker run -e FLAGTREE_VERSION=<ver> <runtime|app image> ...
#
# The request is honoured by this file (every bash shell sources it, and the app
# launchers source it before exec), which installs the wheel into /opt/flagtree
# in place — the path stays fixed, so PYTHONPATH needs no adjustment. Once per
# container: a shell that finds the request already satisfied does nothing.
# ============================================================================

_compiler_side_dirs="/opt/flagtree /opt/triton"

# Where a requested version is fetched from: this image's own vendor index
# (written at build time from the FLAGOS_PYPI build arg), then the shared lane.
# The vendor index is tried first and alone — see _flagtree_install_version.
_flagtree_index_file="/etc/flagos/flagtree-index"
_flagtree_fallback_index="https://resource.flagos.net/repository/flagos-pypi-hosted/simple"

_compiler_active_dir() {
    # Return the compiler dir currently on PYTHONPATH, if any.
    for d in $_compiler_side_dirs; do
        case ":${PYTHONPATH:-}:" in
            *":${d}:"*) echo "$d"; return 0 ;;
        esac
    done
    return 1
}

_compiler_strip_side_dirs() {
    # Drop the compiler side dirs from PYTHONPATH, keep everything else.
    local cleaned=""
    IFS=":"
    for p in ${PYTHONPATH:-}; do
        case " $_compiler_side_dirs " in
            *" $p "*) ;;
            *) [ -n "$cleaned" ] && cleaned="${cleaned}:${p}" || cleaned="$p" ;;
        esac
    done
    printf '%s' "$cleaned"
}

_flagtree_installed_version() {
    # Read the installed dist-info name directly: this runs on every shell
    # start, and starting the interpreter for --version would cost more than
    # the install it guards against.
    local d
    for d in /opt/flagtree/flagtree-*.dist-info; do
        [ -d "$d" ] || continue
        d="${d##*/flagtree-}"
        printf '%s' "${d%.dist-info}"
        return 0
    done
    return 1
}

_flagtree_index_url() {
    local u=""
    [ -r "$_flagtree_index_file" ] && read -r u < "$_flagtree_index_file"
    printf '%s' "${u:-$_flagtree_fallback_index}"
}

_flagtree_install_version() {
    # Install ${1} into /opt/flagtree, leaving the baked tree in place until it
    # succeeded. Returns 1 on failure (caller warns and keeps the default).
    local ver="$1" staged="/opt/flagtree.new" index src ok=1
    local -a sources=()

    command -v pip >/dev/null 2>&1 || { echo "flagtree ${ver}: pip not found" >&2; return 1; }

    # This image's own vendor index first, the shared lane second — sequential
    # attempts, not `--extra-index-url`. Two indexes in one pool let another
    # lane's build win: 0.7.0+tileir3.6 outranks a vendor's plain 0.7.0, so a
    # pooled lookup for `0.6.1` on nvidia took tileir's wheel, which then
    # brought up no driver at all.
    index=$(_flagtree_index_url)
    sources=("$index")
    [ "$index" != "$_flagtree_fallback_index" ] && sources+=("$_flagtree_fallback_index")

    rm -rf "$staged"
    for src in "${sources[@]}"; do
        echo "flagtree ${ver}: installing from ${src} (one-off, ~390 MB)..." >&2
        # --no-deps: /opt/flagtree is FIRST on PYTHONPATH, so a dependency
        # landing there would shadow the venv's pinned stack. The baked tree
        # was installed without deps for the same reason.
        if pip install --no-deps --no-cache-dir --index-url "$src" \
                --target "$staged" "flagtree==${ver}" >&2; then
            ok=0
            break
        fi
        rm -rf "$staged"
    done
    if [ "$ok" -ne 0 ]; then
        echo "flagtree ${ver}: install failed — keeping the baked version" >&2
        echo "  (no egress to the index? pass -e http_proxy=... to docker run)" >&2
        return 1
    fi
    [ -d "$staged/triton" ] || {
        echo "flagtree ${ver}: wheel carries no triton/ — keeping the baked version" >&2
        rm -rf "$staged"
        return 1
    }
    # Swap, with the baked tree kept until the new one is in place.
    rm -rf /opt/flagtree.old
    mv /opt/flagtree /opt/flagtree.old && mv "$staged" /opt/flagtree || {
        [ -d /opt/flagtree ] || mv /opt/flagtree.old /opt/flagtree
        rm -rf "$staged"
        return 1
    }
    rm -rf /opt/flagtree.old
}

_flagtree_version_satisfied() {
    # Does the tree at /opt/flagtree already satisfy the request ${1}? A public
    # request (0.7.0) is satisfied by a lane build of it (0.7.0+metax3.6) — the
    # local segment is a pin only when the caller wrote one.
    local want="$1" have
    have=$(_flagtree_installed_version) || return 1
    [ "$have" = "$want" ] && return 0
    [ "$want" = "${want%%+*}" ] && [ "${have%%+*}" = "$want" ]
}

_flagtree_ensure_version() {
    # Make the requested version the one at /opt/flagtree, if it is not already.
    # Every shell start calls this, so the common case — request already
    # satisfied, or no request at all — has to cost nothing: one readdir, no
    # interpreter start, no network.
    #
    # A container that re-requests the same version in a later shell therefore
    # does nothing, while the *same* version requested in a fresh container is
    # fetched again — which is what makes a rebuilt wheel of an unchanged
    # version reachable.
    local want="${1:-}"
    [ -n "$want" ] || return 0
    _flagtree_version_satisfied "$want" && return 0
    _flagtree_install_version "$want" || return 1
    echo "flagtree ${want}: active" >&2
}

_compiler_import_triton() {
    # Import triton with the given dir first on PYTHONPATH. Strip the other
    # compiler side dir first — prepending over an active default leaves both
    # dirs on PYTHONPATH, and entry-point discovery then imports every
    # declared backend (e.g. mthreads from flagtree vs musa from triton)
    # against whichever triton tree wins package resolution, which fails when
    # that backend only exists in the other tree.
    local cleaned
    cleaned=$(_compiler_strip_side_dirs)
    if [ -n "$cleaned" ]; then
        PYTHONPATH="${1}:${cleaned}" python3 -c \
            "import triton; print(triton.__version__)"
    else
        PYTHONPATH="${1}" python3 -c \
            "import triton; print(triton.__version__)"
    fi
}

compiler() {
    local dir=""

    case "${1:-}" in
        flagtree)
            if [ -n "${2:-}" ]; then
                # Install-on-demand: the one-off cost is the reason a FlagTree
                # bump no longer forces a rebuild of every image above this one.
                _flagtree_ensure_version "$2" || return 1
            fi
            if [ ! -d /opt/flagtree/triton ]; then
                echo "flagtree: not available on this backend" >&2
                return 1
            fi
            dir="/opt/flagtree"
            ;;
        triton)
            if [ ! -d /opt/triton/triton ]; then
                echo "triton: not available on this backend" >&2
                return 1
            fi
            dir="/opt/triton"
            ;;
        ""|status|help)
            # Show availability + what's active, and make sure the default
            # compiler is on PYTHONPATH (idempotent re-export).
            echo "available compilers:"
            if [ -d /opt/flagtree/triton ]; then
                # flagtree's own version, not triton.__version__: both trees
                # report the Triton line they forked, so only the dist name
                # tells the two FlagTree builds apart.
                echo "  flagtree  $(_flagtree_installed_version) (triton $(_compiler_import_triton /opt/flagtree))  (default)"
            fi
            if [ -d /opt/triton/triton ]; then
                echo "  triton    $(_compiler_import_triton /opt/triton)"
            fi
            if ! _compiler_active_dir >/dev/null; then
                # No side dir on PYTHONPATH — default to flagtree when
                # present, else triton.  Keeps the image usable with zero
                # user action and restores the default after an explicit
                # 'compiler' with no args.
                if [ -d /opt/flagtree/triton ]; then
                    dir="/opt/flagtree"
                elif [ -d /opt/triton/triton ]; then
                    dir="/opt/triton"
                fi
            fi
            ;;
        *)
            echo "Usage: compiler [flagtree|triton] [version]" >&2
            echo "  compiler                  show status" >&2
            echo "  compiler flagtree         switch to FlagTree (default)" >&2
            echo "  compiler triton           switch to Triton" >&2
            echo "  compiler flagtree <ver>   install that FlagTree version, then switch to it" >&2
            return 1
            ;;
    esac

    if [ -n "$dir" ]; then
        local cleaned
        cleaned=$(_compiler_strip_side_dirs)
        if [ -n "$cleaned" ]; then
            export PYTHONPATH="${dir}:${cleaned}"
        else
            export PYTHONPATH="${dir}"
        fi
        echo "$(basename "$dir") (active) - $(_compiler_import_triton "$dir")"
    else
        echo "active compiler:"
        local active
        if active=$(_compiler_active_dir); then
            python3 -c "import os, triton; print(' ', os.path.basename(os.path.dirname(os.path.dirname(triton.__file__))), '-', triton.__version__)"
        else
            echo "  (no compiler side dir on PYTHONPATH)"
        fi
    fi
}

# FLAGTREE_VERSION, when set, is a version request made at container start.
# Call it in the condition position: the launchers run `set -e`, and an
# unreachable index or an unpublished version must leave the baked default
# working rather than abort the shell that is about to exec the server.
if ! _flagtree_ensure_version "${FLAGTREE_VERSION:-}"; then
    echo "FLAGTREE_VERSION=${FLAGTREE_VERSION:-}: keeping the version baked into this image" >&2
fi

# Keep the default compiler active in every new shell.
if ! _compiler_active_dir >/dev/null; then
    if [ -d /opt/flagtree/triton ]; then
        export PYTHONPATH="/opt/flagtree${PYTHONPATH:+:}${PYTHONPATH:-}"
    elif [ -d /opt/triton/triton ]; then
        export PYTHONPATH="/opt/triton${PYTHONPATH:+:}${PYTHONPATH:-}"
    fi
fi
