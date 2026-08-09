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
#   compiler             — show what's available and what's active
#   compiler flagtree    — switch to FlagTree (default when present)
#   compiler triton      — switch to the vendor Triton
# ============================================================================

_compiler_side_dirs="/opt/flagtree /opt/triton"

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

_compiler_import_triton() {
    # Import triton with the given dir first on PYTHONPATH.
    PYTHONPATH="${1}${PYTHONPATH:+:}${PYTHONPATH:-}" python3 -c \
        "import triton; print(triton.__version__)"
}

compiler() {
    local dir=""

    case "${1:-}" in
        flagtree)
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
                echo "  flagtree  $(_compiler_import_triton /opt/flagtree)  (default)"
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
            echo "Usage: compiler [flagtree|triton]" >&2
            echo "  compiler           show status" >&2
            echo "  compiler flagtree  switch to FlagTree (default)" >&2
            echo "  compiler triton    switch to Triton" >&2
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

# Keep the default compiler active in every new shell.
if ! _compiler_active_dir >/dev/null; then
    if [ -d /opt/flagtree/triton ]; then
        export PYTHONPATH="/opt/flagtree${PYTHONPATH:+:}${PYTHONPATH:-}"
    elif [ -d /opt/triton/triton ]; then
        export PYTHONPATH="/opt/triton${PYTHONPATH:+:}${PYTHONPATH:-}"
    fi
fi
