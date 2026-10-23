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
#   compiler flagtree latest — install this backend's newest daily build
#
# FlagTree releases on its own cadence, and a bump would otherwise mean
# rebuilding every image above the runtime. So a different version can also be
# requested at container start, before any launcher exec's:
#
#   docker run -e FLAGTREE_VERSION=<ver|latest> <runtime|app image> ...
#
# The request is honoured by this file (every bash shell sources it, and the app
# launchers source it before exec), which installs the wheel into /opt/flagtree
# in place — the path stays fixed, so PYTHONPATH needs no adjustment.
#
# <ver> is a release, fetched from this image's vendor index. `latest` is the
# daily line (flagos-pypi-daily), under the distribution name this backend's
# image was built with — a different, per-backend project name, so the tree is
# replaced wholesale and the dist-info changes name with it. Once per container:
# a shell that finds the request already satisfied does nothing, so a later
# shell in the same container neither re-fetches nor goes to the network, while
# the next container picks up whatever the daily line published since.
#
# A request that cannot be honoured STOPS the container. Someone who asks for a
# version and silently gets another one is running a stack they did not ask for,
# and nothing downstream would tell them — so the failure is reported and the
# exit is non-zero, which is what a container runtime (and so kubectl, and so an
# operator) treats as a failed start. Docker reports the code; under kubernetes
# the pod goes to Error/CrashLoopBackOff instead of coming up Running on the
# wrong compiler, with `kubectl logs <pod> [--previous]` carrying the reason.
# The runtime and the app images both end in bash, so both exit this way, and no
# launcher is exec'd when the request could not be met.
# ============================================================================

_compiler_side_dirs="/opt/flagtree /opt/triton"

# Where a requested version is fetched from: this image's own vendor index
# (written at build time from the FLAGOS_PYPI build arg), then the shared lane.
# The vendor index is tried first and alone — see _flagtree_install_version.
_flagtree_index_file="/etc/flagos/flagtree-index"
_flagtree_fallback_index="https://resource.flagos.net/repository/flagos-pypi-hosted/simple"

# The daily line, for `latest`: this backend's distribution name on line 1 and
# the daily index on line 2, both written at build time from the
# FLAGTREE_DAILY_PKG / DAILY_PYPI build args. The file is absent on the
# backends the daily line does not build, which is how `latest` knows to refuse
# rather than guess a name.
_flagtree_daily_file="/etc/flagos/flagtree-daily"

# Records what `latest` resolved to, so the rest of the container's shells skip
# the fetch. Inside the tree rather than beside it: the install replaces
# /opt/flagtree wholesale, so a later explicit version request clears it for
# free and no stale marker can outlive the build it described.
_flagtree_daily_marker="/opt/flagtree/.daily-latest"

# The request that could not be honoured in this container. Not "impossible" but
# "already settled once": every shell start reads it and gives up immediately,
# so the failure is reported by the shell that is about to exec the server and
# not paid for again — or repeated — by the ones behind it.
_flagtree_failed_file="/opt/flagtree/.request-failed"

# Bound the network wait of an install — a launch must not sit on an index that
# is not answering. pip's default (5 retries x 15s connect) measured 103s against
# a blackholed index; one retry measured 36s, and the healthy path is unaffected
# (2.0s -> 2.6s). Every retry is a fresh cache entry anyway, since these installs
# run with --no-cache-dir.
_flagtree_pip_net_opts=(--retries 1 --timeout 15)

# Reachability pre-flight, asked before pip is allowed to try. A blackholed index
# costs a 15s connect timeout per pip attempt (measured 36s for the bounded set
# above); curl is asked only to open the connection, which answered in 3.5s for
# the same blackhole and 0.5s when healthy. What comes back decides the message:
# an unroutable index and a healthy index that simply lacks the wheel are
# different problems and must not print the same text.
_flagtree_probe_timeout=10

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

_flagtree_installed_dist() {
    # The installed dist-info's basename, name and version joined: what the tree
    # was installed as. Any *.dist-info, not `flagtree-*` — the daily line
    # publishes one project per backend, so a tree installed from it carries
    # `flagtree_nvidia-<ver>` or `flagtree_ascend_cann9_0_0-<ver>` instead. The
    # tree holds a compiler and nothing else, so whatever dist-info is in it is
    # the one to report.
    local d
    for d in /opt/flagtree/*.dist-info; do
        [ -d "$d" ] || continue
        d="${d##*/}"
        printf '%s' "${d%.dist-info}"
        return 0
    done
    return 1
}

_flagtree_installed_version() {
    # Version alone. Read from the dist-info name rather than the interpreter:
    # this runs on every shell start, and `python3 -c import` would cost more
    # than the install it guards against. Name and version are joined by the
    # LAST `-` (a normalized version never carries one), so the project prefix —
    # whichever spelling the tree was installed under — drops off either way.
    local dist
    dist=$(_flagtree_installed_dist) || return 1
    printf '%s' "${dist##*-}"
}

_flagtree_installed_is_daily() {
    # Was the tree at /opt/flagtree installed from the daily line? Its project
    # names are the escaped ones (`flagtree_nvidia`), and a normalized project
    # name never carries `_` — which is how they are told from the release
    # line's `flagtree`.
    local dist
    dist=$(_flagtree_installed_dist) || return 1
    dist="${dist%-*}"
    [ "${dist#*_}" != "$dist" ]
}

_flagtree_mark_failed() {
    # Remember, for this container only, that ${1} could not be installed. The
    # file sits inside the tree, so a later successful install replaces it away.
    printf '%s\n' "$1" > "$_flagtree_failed_file"
}

_flagtree_clear_failed() {
    rm -f "$_flagtree_failed_file"
}

_flagtree_report_unreachable() {
    # Say which index is not answering and what the user can do about it. The
    # request is about to be refused, so the conclusion — not a pip log — is what
    # has to reach them.
    local what="$1" url="$2" why="$3"
    echo "flagtree ${what}: cannot reach the index" >&2
    echo "  index:   ${url}" >&2
    echo "  reason:  ${why}" >&2
    echo "  fix:     no egress from this container? pass -e https_proxy=... -e no_proxy=..." >&2
}

_flagtree_report_cannot_install() {
    # The request is refused: the container is about to stop, so this is the last
    # word on the subject and it has to say what to do next.
    local what="$1"
    echo "flagtree ${what}: cannot install the requested version — stopping" >&2
    echo "  a container running a different FlagTree than the one requested is not what was asked for" >&2
    echo "  fix:     drop -e FLAGTREE_VERSION to run the version baked into this image, or make the index reachable" >&2
}

_flagtree_unreachable_reason() {
    # Human sentence for why the probe's request failed, from curl's own words.
    case "$1" in
        *'Could not resolve'*) echo "the index host does not resolve (DNS)" ;;
        *'timed out'*)         echo "no answer within ${_flagtree_probe_timeout}s (no route to it?)" ;;
        *)                     echo "no answer within ${_flagtree_probe_timeout}s" ;;
    esac
}

_flagtree_pip_install() {
    # pip, but not at the cost of explaining a dead network: an index that does
    # not answer is settled by one short connection attempt, and the caller gets
    # the URL and the reason rather than a wall of retry warnings. Returns 2 when
    # the index was unreachable (already reported), pip's own status otherwise.
    local what="$1" index="$2" why
    shift 2
    if command -v curl >/dev/null 2>&1; then
        if ! why=$(curl -sS -o /dev/null --connect-timeout "$_flagtree_probe_timeout" \
                       --max-time "$_flagtree_probe_timeout" "$index" 2>&1); then
            _flagtree_report_unreachable "$what" "$index" \
                "$(_flagtree_unreachable_reason "$why")"
            return 2
        fi
    fi
    pip install "${_flagtree_pip_net_opts[@]}" "$@"
}

_flagtree_index_url() {
    local u=""
    [ -r "$_flagtree_index_file" ] && read -r u < "$_flagtree_index_file"
    printf '%s' "${u:-$_flagtree_fallback_index}"
}

_flagtree_swap_in() {
    # Put the staged tree at /opt/flagtree, keeping the current one until the
    # new one is in place. Carries no state across: the marker for `latest`
    # lives inside the tree, so whatever the old build recorded leaves with it.
    local staged="$1"
    rm -rf /opt/flagtree.old
    mv /opt/flagtree /opt/flagtree.old && mv "$staged" /opt/flagtree || {
        [ -d /opt/flagtree ] || mv /opt/flagtree.old /opt/flagtree
        rm -rf "$staged"
        return 1
    }
    rm -rf /opt/flagtree.old
}

_flagtree_install_version() {
    # Install ${1} into /opt/flagtree, leaving the baked tree in place until it
    # succeeded. Returns 1 on failure (caller warns and keeps the default).
    local ver="$1" staged="/opt/flagtree.new" index src ok=1 reachable=0
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
        # --no-deps: /opt/flagtree is FIRST on PYTHONPATH, and pip does not treat
        # what the venv already has as satisfying a --target install, so a
        # dependency landing here would shadow the venv's pinned copy with
        # whatever the index serves. FlagTree declares none today. Its declared
        # dependencies, if it ever gains any, belong in the venv, where the
        # resolver can see the pinned stack. #1481.
        # Exit 2 means the index was unreachable and has been reported; the other
        # source is still worth trying, since the two need not be the same host.
        local rc=0
        _flagtree_pip_install "$ver" "$src" --no-deps --no-cache-dir \
                --index-url "$src" --target "$staged" "flagtree==${ver}" >&2 || rc=$?
        if [ "$rc" -eq 0 ]; then
            ok=0
            break
        fi
        [ "$rc" -eq 2 ] || reachable=1
        rm -rf "$staged"
    done
    if [ "$ok" -ne 0 ]; then
        # Only claim the index answered when one actually did.
        [ "$reachable" -eq 1 ] && echo "flagtree ${ver}: the index has no such version" >&2
        return 1
    fi
    [ -d "$staged/triton" ] || {
        echo "flagtree ${ver}: wheel carries no triton/ — not a FlagTree build" >&2
        rm -rf "$staged"
        return 1
    }
    _flagtree_swap_in "$staged"
}

_flagtree_install_daily() {
    # Install this backend's newest daily build into /opt/flagtree.
    #
    # The daily line publishes one project per backend under its own name
    # (flagtree-nvidia, flagtree-hcu, ...), so this is a DIFFERENT distribution
    # from the release line's `flagtree` rather than a newer version of it: pip
    # treats the two as unrelated projects, and installing one over the other is
    # a file-level clobber. Replacing the tree wholesale is what makes that
    # safe — the dist-info changes name with it, and nothing reads the old one
    # afterwards (_flagtree_installed_version takes whatever is in the tree).
    local dist="" index="" staged="/opt/flagtree.new"

    if [ ! -r "$_flagtree_daily_file" ] ||
       ! { read -r dist; read -r index; } < "$_flagtree_daily_file" ||
       [ -z "$dist" ] || [ -z "$index" ]; then
        echo "flagtree latest: this backend has no daily line — request an explicit version" >&2
        return 1
    fi
    command -v pip >/dev/null 2>&1 || { echo "flagtree latest: pip not found" >&2; return 1; }

    rm -rf "$staged"
    echo "flagtree latest: installing ${dist} from ${index} (one-off, ~124 MB)..." >&2
    # No version specifier: pip takes the newest the project offers. --pre is
    # what admits a `.dev<date>` at all — without it every daily is invisible.
    # The daily index is a separate repository, so it never shares a resolution
    # pool with the vendor index (the same reason _flagtree_install_version
    # walks its sources sequentially instead of using --extra-index-url).
    local rc=0
    _flagtree_pip_install latest "$index" --pre --no-deps --no-cache-dir \
            --index-url "$index" --target "$staged" "$dist" >&2 || rc=$?
    if [ "$rc" -ne 0 ]; then
        rm -rf "$staged"
        # 2 = the probe already reported it, and said why. Anything else is the
        # index answering "no such project", which the user has to be told.
        [ "$rc" -eq 2 ] || echo "flagtree latest: the daily index has no ${dist}" >&2
        return 1
    fi
    [ -d "$staged/triton" ] || {
        echo "flagtree latest: wheel carries no triton/ — not a FlagTree build" >&2
        rm -rf "$staged"
        return 1
    }
    _flagtree_swap_in "$staged" || return 1
    # Drop the marker inside the tree just installed: the next shell in this
    # container sees it and skips the fetch. Written only once there is a version
    # to record — an empty file would read as "already fetched" for a tree that
    # has nothing, and the fetch would never be retried in this container.
    local ver
    ver=$(_flagtree_installed_version) || return 1
    printf '%s\n' "$ver" > "$_flagtree_daily_marker"
}

_flagtree_version_satisfied() {
    # Does the tree at /opt/flagtree already satisfy the request ${1}? A public
    # request (0.7.0) is satisfied by a lane build of it (0.7.0+metax3.6) — the
    # local segment is a pin only when the caller wrote one.
    #
    # A version request only ever means the release line: a daily is not a newer
    # form of it but a different project, so it never satisfies one (nor the
    # reverse — `latest` has no version form and is handled by the caller).
    local want="$1" have
    if _flagtree_installed_is_daily; then return 1; fi
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
    local want="${1:-}" force="${2:-}"
    [ -n "$want" ] || return 0

    # A request that already failed in this container is not retried by every
    # later shell: the failure does not become a success by asking again, and
    # every one of them would pay the wait. Each reports it and stops, so the
    # container fails the same way whichever shell got there first. Asking by
    # hand (compiler flagtree <ver>) passes force and tries regardless.
    if [ -z "$force" ] && [ -r "$_flagtree_failed_file" ] &&
       [ "$(cat "$_flagtree_failed_file")" = "$want" ]; then
        echo "flagtree ${want}: the request already failed in this container" >&2
        return 1
    fi

    if [ "$want" = latest ]; then
        # The daily line moves without any version being named, so "already
        # satisfied" cannot be decided from the tree — the tree is at whatever
        # the last fetch picked. The marker is what makes the answer per
        # container instead of per shell: present means this container already
        # fetched, absent means it has not. A long-running container therefore
        # stays on the build it started with; the next one gets the newer.
        [ -f "$_flagtree_daily_marker" ] && return 0
        if _flagtree_install_daily; then
            _flagtree_clear_failed
            echo "flagtree latest: $(_flagtree_installed_version) active" >&2
            return 0
        fi
        _flagtree_mark_failed "$want"
        return 1
    fi

    # An explicit version replaces whatever `latest` installed, and the swap
    # takes the marker with it — so the next `latest` request in this container
    # fetches again rather than trusting a marker for a build that is gone.
    _flagtree_version_satisfied "$want" && return 0
    if _flagtree_install_version "$want"; then
        _flagtree_clear_failed
        echo "flagtree ${want}: active" >&2
        return 0
    fi
    _flagtree_mark_failed "$want"
    return 1
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
                # By hand, so it retries even where container start gave up.
                _flagtree_ensure_version "$2" force || return 1
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
            echo "Usage: compiler [flagtree|triton] [version|latest]" >&2
            echo "  compiler                  show status" >&2
            echo "  compiler flagtree         switch to FlagTree (default)" >&2
            echo "  compiler triton           switch to Triton" >&2
            echo "  compiler flagtree <ver>   install that FlagTree version, then switch to it" >&2
            echo "  compiler flagtree latest  install this backend's newest daily build" >&2
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

# FLAGTREE_VERSION, when set, is a version request made at container start. A
# request that cannot be honoured stops the container: someone who asked for a
# version and silently got another one is running a stack they did not ask for,
# and nothing downstream would say so. The non-zero exit is what makes the
# failure visible to a container runtime — `docker run` reports it, and under
# kubernetes it is what turns the reason in `kubectl logs` into a pod that is
# visibly not running rather than one serving on the wrong compiler.
if ! _flagtree_ensure_version "${FLAGTREE_VERSION:-}"; then
    _flagtree_report_cannot_install "${FLAGTREE_VERSION:-}"
    exit 1
fi

# Keep the default compiler active in every new shell.
if ! _compiler_active_dir >/dev/null; then
    if [ -d /opt/flagtree/triton ]; then
        export PYTHONPATH="/opt/flagtree${PYTHONPATH:+:}${PYTHONPATH:-}"
    elif [ -d /opt/triton/triton ]; then
        export PYTHONPATH="/opt/triton${PYTHONPATH:+:}${PYTHONPATH:-}"
    fi
fi
