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
# zz-flagos.sh — baked into /etc/profile.d of every runtime image.
#
# The zz- prefix sorts it LAST among /etc/profile.d/*.sh, after any vendor.sh
# that assigns PYTHONPATH absolutely (ascend's set_env.sh capture does) — which
# would otherwise clobber the compiler side dirs off PYTHONPATH. FlagTree
# (/opt/flagtree, default) and the vendor Triton (/opt/triton) are not in
# site-packages, so they are reachable only through PYTHONPATH.
#
#   compiler [flagtree|triton] [version|latest]
#   docker run -e FLAGTREE_VERSION=<ver|latest> <runtime|app image> ...
#   docker run -e FLAGGEMS_VERSION=<ver|latest> <runtime|app image> ...
#
# A request that cannot be honoured STOPS the container: running a different
# FlagTree than the one asked for is a stack the caller did not ask for.
# ============================================================================

_compiler_side_dirs="/opt/flagtree /opt/triton"

# Per-package facts the shared code needs, as one-line case arms: where the
# `latest` fetch is recorded, where a refusal is remembered, what the messages
# call the package, and which env var carries the request. A package joins by
# adding an arm to each and defining _<pkg>_satisfied, _<pkg>_install_exact,
# _<pkg>_install_latest and _<pkg>_installed_version.
_flagos_pkg_marker() {
    case "$1" in
        flagtree) printf '%s' "/opt/flagtree/.daily-latest" ;;
        flaggems) printf '%s' "/flagos/.flaggems-latest" ;;
    esac
}

_flagos_pkg_failed() {
    case "$1" in
        # Inside the tree for FlagTree: the install replaces it wholesale, so a
        # later explicit version request clears this for free.
        flagtree) printf '%s' "/opt/flagtree/.request-failed" ;;
        flaggems) printf '%s' "/flagos/.flaggems-request-failed" ;;
    esac
}

_flagos_pkg_label() {
    case "$1" in
        flagtree) printf '%s' "FlagTree" ;;
        flaggems) printf '%s' "FlagGems" ;;
    esac
}

_flagos_pkg_envvar() {
    case "$1" in
        flagtree) printf '%s' "FLAGTREE_VERSION" ;;
        flaggems) printf '%s' "FLAGGEMS_VERSION" ;;
    esac
}

# Read from this image's own vendor index (written at build time from the
# FLAGOS_PYPI / DAILY_PYPI build args).
_flagos_vendor_index_file="/etc/flagos/vendor-index"
_flagos_vendor_fallback_index="https://resource.flagos.net/repository/flagos-pypi-hosted/simple"
_flagos_daily_index_file="/etc/flagos/daily-index"
_flagos_mirror_index_file="/etc/flagos/mirror-index"

# The daily line, for `latest`: only this package's per-backend distribution
# name, written at build time from FLAGTREE_DAILY_PKG. Absent on the backends
# the daily line does not build, which is how `latest` knows to refuse rather
# than guess a name.
_flagtree_daily_file="/etc/flagos/flagtree-daily"

# Bound the network wait of an install — a launch must not sit on an index that
# is not answering. pip's default (5 retries x 15s connect) measured 103s against
# a blackholed index; one retry measured 36s, and the healthy path is unaffected
# (2.0s -> 2.6s). Every retry is a fresh cache entry anyway, since these installs
# run with --no-cache-dir.
_flagos_pip_net_opts=(--retries 1 --timeout 15)

# Reachability pre-flight, asked before pip is allowed to try: curl is asked only
# to open the connection, which answered in 3.5s for the same blackhole that cost
# pip 36s. What comes back decides the message — an unroutable index and a
# healthy index that simply lacks the wheel are different problems.
_flagos_probe_timeout=10

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
    # The installed dist-info's basename, name and version joined. Any
    # *.dist-info, not `flagtree-*`: the daily line's per-backend names
    # (`flagtree_nvidia-<ver>`) install into this same tree.
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

_flagos_mark_failed() {
    # Remember, for this container only, that the request could not be honoured.
    printf '%s\n' "$2" > "$(_flagos_pkg_failed "$1")"
}

_flagos_clear_failed() {
    rm -f "$(_flagos_pkg_failed "$1")"
}

_flagos_report_unreachable() {
    # Say which index is not answering and what the user can do about it. The
    # request is about to be refused, so the conclusion — not a pip log — is what
    # has to reach them.
    local pkg="$1" what="$2" url="$3" why="$4"
    echo "${pkg} ${what}: cannot reach the index" >&2
    echo "  index:   ${url}" >&2
    echo "  reason:  ${why}" >&2
    echo "  fix:     no egress from this container? pass -e https_proxy=... -e no_proxy=..." >&2
}

_flagos_report_cannot_install() {
    # The request is refused: the container is about to stop, so this is the last
    # word on the subject and it has to say what to do next.
    local pkg="$1" what="$2" envvar
    envvar=$(_flagos_pkg_envvar "$pkg")
    echo "$(_flagos_pkg_label "$pkg") ${what}: cannot install the requested version — stopping" >&2
    echo "  a container running a different $(_flagos_pkg_label "$pkg") than the one requested is not what was asked for" >&2
    echo "  fix:     drop -e ${envvar} to run the version baked into this image, or make the index reachable" >&2
}

_flagos_unreachable_reason() {
    # Human sentence for why the probe's request failed, from curl's own words.
    case "$1" in
        *'Could not resolve'*) echo "the index host does not resolve (DNS)" ;;
        *'timed out'*)         echo "no answer within ${_flagos_probe_timeout}s (no route to it?)" ;;
        *)                     echo "no answer within ${_flagos_probe_timeout}s" ;;
    esac
}

_flagos_probe() {
    # 0 when the index opens a connection, 2 when it does not (reported here).
    local pkg="$1" what="$2" url="$3" why
    command -v curl >/dev/null 2>&1 || return 0
    if ! why=$(curl -sS -o /dev/null --connect-timeout "$_flagos_probe_timeout" \
                   --max-time "$_flagos_probe_timeout" "$url" 2>&1); then
        _flagos_report_unreachable "$pkg" "$what" "$url" \
            "$(_flagos_unreachable_reason "$why")"
        return 2
    fi
    return 0
}

_flagos_pip_install() {
    # pip, but not at the cost of explaining a dead network: the index is probed
    # first, so an index that does not answer is settled by one short connection
    # attempt and the caller gets the URL and the reason rather than a wall of
    # retry warnings. Returns 2 when unreachable, pip's own status otherwise.
    local pkg="$1" what="$2" index="$3" rc=0
    shift 3
    _flagos_probe "$pkg" "$what" "$index" || rc=$?
    [ "$rc" -eq 0 ] || return "$rc"
    pip install "${_flagos_pip_net_opts[@]}" "$@"
}

_flagos_index_vendor() {
    local u=""
    [ -r "$_flagos_vendor_index_file" ] && read -r u < "$_flagos_vendor_index_file"
    printf '%s' "${u:-$_flagos_vendor_fallback_index}"
}

_flagos_index_daily() {
    local u=""
    [ -r "$_flagos_daily_index_file" ] && read -r u < "$_flagos_daily_index_file"
    printf '%s' "$u"
}

_flagos_index_mirror() {
    local u=""
    [ -r "$_flagos_mirror_index_file" ] && read -r u < "$_flagos_mirror_index_file"
    printf '%s' "$u"
}

# The versions this image itself pins (configs.yaml deps + runtime_prereqs),
# frozen at build time. An in-container FlagGems install resolves against a pool
# that has to reach the public mirror — vendor indexes carry no numpy, the daily
# index 14 projects — and the mirror offers numpy 2.x, an ABI break under a torch
# built for 1.x. FlagGems' own transitive deps are deliberately absent: an older
# release legitimately moves those.
_flagos_flaggems_constraints="/etc/flagos/flaggems-constraints.txt"

_flagos_same_version() {
    # A public request (0.7.0) is satisfied by a lane build of it (0.7.0+metax3.6)
    # — the local segment is a pin only when the caller wrote one.
    local want="$1" have="$2"
    [ "$have" = "$want" ] && return 0
    [ "$want" = "${want%%+*}" ] && [ "${have%%+*}" = "$want" ]
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

_flagtree_install_exact() {
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
    index=$(_flagos_index_vendor)
    sources=("$index")
    [ "$index" != "$_flagos_vendor_fallback_index" ] && sources+=("$_flagos_vendor_fallback_index")

    rm -rf "$staged"
    for src in "${sources[@]}"; do
        echo "flagtree ${ver}: installing from ${src} (one-off, ~390 MB)..." >&2
        # --no-deps: /opt/flagtree is FIRST on PYTHONPATH, so a dependency
        # landing here would shadow the venv's pinned copy. #1481.
        # Exit 2 means the index was unreachable and has been reported; the other
        # source is still worth trying, since the two need not be the same host.
        local rc=0
        _flagos_pip_install flagtree "$ver" "$src" --no-deps --no-cache-dir \
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

_flagtree_install_latest() {
    # Install this backend's newest daily build into /opt/flagtree. The daily
    # line's per-backend project names are DIFFERENT distributions from the
    # release line's `flagtree` rather than newer versions of it, so installing
    # one over the other is a file-level clobber. Replacing the tree wholesale
    # is what makes that safe: the dist-info changes name with it.
    local dist="" index="" staged="/opt/flagtree.new"

    if [ ! -r "$_flagtree_daily_file" ] || ! read -r dist < "$_flagtree_daily_file" ||
       [ -z "$dist" ]; then
        echo "flagtree latest: this backend has no daily line — request an explicit version" >&2
        return 1
    fi
    index=$(_flagos_index_daily)
    if [ -z "$index" ]; then
        echo "flagtree latest: no daily index in this image — request an explicit version" >&2
        return 1
    fi
    command -v pip >/dev/null 2>&1 || { echo "flagtree latest: pip not found" >&2; return 1; }

    rm -rf "$staged"
    echo "flagtree latest: installing ${dist} from ${index} (one-off, ~124 MB)..." >&2
    # No version specifier: pip takes the newest the project offers. --pre is
    # what admits a `.dev<date>` at all — without it every daily is invisible.
    # The daily index is a separate repository, so it never shares a resolution
    # pool with the vendor index (the same reason _flagtree_install_exact walks
    # its sources sequentially instead of using --extra-index-url).
    local rc=0
    _flagos_pip_install flagtree latest "$index" --pre --no-deps --no-cache-dir \
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
    printf '%s\n' "$ver" > "$(_flagos_pkg_marker flagtree)"
}

_flagtree_satisfied() {
    # Does the tree at /opt/flagtree already satisfy the request ${1}?
    #
    # A version request only ever means the release line: a daily is not a newer
    # form of it but a different project, so it never satisfies one (nor the
    # reverse — `latest` has no version form, see _flagos_ensure).
    local want="$1" have
    if _flagtree_installed_is_daily; then return 1; fi
    have=$(_flagtree_installed_version) || return 1
    _flagos_same_version "$want" "$have"
}

_flaggems_installed_version() {
    # Version alone, read off the dist-info name: this runs on every shell start,
    # and `python3` is ambiguous in this image (the venv's, and the vendor's).
    local d
    for d in /flagos/lib/python3.*/site-packages/flag_gems-*.dist-info; do
        [ -d "$d" ] || continue
        d="${d##*/}"
        d="${d%.dist-info}"
        printf '%s' "${d#flag_gems-}"
        return 0
    done
    return 1
}

_flaggems_satisfied() {
    # FlagGems has one project name on every lane, so — unlike FlagTree — what is
    # installed answers the request directly, whatever line it came from.
    local want="$1" have
    have=$(_flaggems_installed_version) || return 1
    _flagos_same_version "$want" "$have"
}

_flaggems_resolve_latest() {
    # Print the newest version on the daily line, or fail having said why.
    #
    # Read out and installed exactly, rather than handed to pip as a bare name:
    # without --upgrade pip calls an installed 5.4.0 satisfying and does nothing,
    # and with --upgrade it means "newest in the pool", which reaches the public
    # mirror. Both are a different question from the one asked.
    local index out ver
    index=$(_flagos_index_daily)
    if [ -z "$index" ]; then
        echo "flaggems latest: no daily index in this image — request an explicit version" >&2
        return 1
    fi
    command -v pip >/dev/null 2>&1 || { echo "flaggems latest: pip not found" >&2; return 1; }

    _flagos_probe flaggems latest "$index" || return 1
    # pip's own answer rather than a scan of the simple index: the daily line
    # carries both `.dev<date>` builds and releases, and picking the largest by
    # date suffix gets it wrong the moment a release is in there. Only the daily
    # index is asked — it alone decides what `latest` means.
    if ! out=$(pip index versions flag_gems --pre --no-cache-dir \
                   "${_flagos_pip_net_opts[@]}" --index-url "$index" 2>/dev/null); then
        echo "flaggems latest: the daily index has no flag_gems" >&2
        return 1
    fi
    # First line is `flag_gems (5.5.0.dev<date>)`; nothing after it is read.
    read -r _ ver <<<"$out"
    ver="${ver#(}"
    ver="${ver%)}"
    # pip marks this output experimental, so the shape is checked before the
    # string is allowed anywhere near a version specifier.
    case "$ver" in
        [0-9]*)
            case "$ver" in
                *[!0-9A-Za-z.+-]*)
                    echo "flaggems latest: cannot read a version out of the daily index — request an explicit version" >&2
                    return 1 ;;
            esac ;;
        *)
            echo "flaggems latest: cannot read a version out of the daily index — request an explicit version" >&2
            return 1 ;;
    esac
    printf '%s' "$ver"
}

_flaggems_install_exact() {
    # pip replaces the package in place — the wheel is py3-none-any and the venv
    # is the landing point, so unlike FlagTree there is no tree to stage and swap.
    # ${2} is the index expected to hold it, first in the pool and the one probed;
    # the other two follow so dependencies can resolve.
    local ver="$1" index="${2:-}" args=() m have
    [ -n "$index" ] || index=$(_flagos_index_vendor)
    # The same three-index pool the build step resolves against. It has to reach
    # the mirror: the daily index carries 14 projects and the vendor indexes carry
    # no numpy at all.
    for m in "$(_flagos_index_vendor)" "$(_flagos_index_daily)" "$(_flagos_index_mirror)"; do
        [ -n "$m" ] && [ "$m" != "$index" ] && args+=(--extra-index-url "$m")
    done
    if [ -r "$_flagos_flaggems_constraints" ]; then
        args+=(-c "$_flagos_flaggems_constraints")
    else
        # Only reachable with a newer script than image (a bind-mount). Say so —
        # without the file the pool is free to move the stack around FlagGems.
        echo "flaggems ${ver}: no constraints file in this image, the install may move other packages" >&2
    fi

    echo "flaggems ${ver}: installing from ${index} (one-off, ~13 MB)..." >&2
    # --pre: a daily is a `.dev<date>` and invisible without it. No --upgrade:
    # with a bare name that would mean "newest in the pool", which is exactly the
    # question `latest` is not asking. No --no-deps either — unlike the FlagTree
    # tree, site-packages is where the venv's own dependencies belong.
    local rc=0
    _flagos_pip_install flaggems "$ver" "$index" --no-cache-dir --pre \
            --index-url "$index" "${args[@]}" "flag_gems==${ver}" >&2 || rc=$?
    if [ "$rc" -ne 0 ]; then
        # 2 = the probe reported it and already said why. Otherwise the reason is
        # pip's own — a version the pool does not have, or a dependency the
        # constraints file holds below what this FlagGems asks for, and guessing
        # which would be worse than pointing at the output above.
        [ "$rc" -eq 2 ] || echo "flaggems ${ver}: the install failed (pip's reason above)" >&2
        return 1
    fi
    # A pip return of 0 only says it did not give up; the request is what the venv
    # has to end up holding.
    have=$(_flaggems_installed_version) || true
    if [ "$have" != "$ver" ]; then
        echo "flaggems ${ver}: pip succeeded but the venv holds ${have:-nothing}" >&2
        return 1
    fi
}

_flaggems_install_latest() {
    local ver
    ver=$(_flaggems_resolve_latest) || return 1
    echo "flaggems latest: the daily line's newest is ${ver}" >&2
    _flaggems_install_exact "$ver" "$(_flagos_index_daily)" || return 1
    # Record the resolved version so the rest of this container skips the lookup,
    # and report it: `latest` is the newest on the daily line, not the newest this
    # container has seen, so which one was taken is the whole answer.
    printf '%s\n' "$ver" > "$(_flagos_pkg_marker flaggems)"
}

_flagos_ensure() {
    # Make the requested version of ${1} the installed one, if it is not already.
    # Every shell start calls this, so the common case — request already
    # satisfied, or no request at all — has to cost nothing: one readdir, no
    # interpreter start, no network. The same version in a fresh container is
    # still fetched again, which is what makes a rebuilt wheel reachable.
    local pkg="$1" want="${2:-}" force="${3:-}"
    local marker failed
    [ -n "$want" ] || return 0
    marker=$(_flagos_pkg_marker "$pkg")
    failed=$(_flagos_pkg_failed "$pkg")

    # A request that already failed in this container is not retried by every
    # later shell: the failure does not become a success by asking again, and
    # every one of them would pay the wait. Each reports it and stops, so the
    # container fails the same way whichever shell got there first. Asking by
    # hand (compiler flagtree <ver>) passes force and tries regardless.
    if [ -z "$force" ] && [ -r "$failed" ] && [ "$(cat "$failed")" = "$want" ]; then
        echo "${pkg} ${want}: the request already failed in this container" >&2
        return 1
    fi

    if [ "$want" = latest ]; then
        # Nothing installed can answer "already satisfied" for a moving target,
        # so the marker is what makes the answer per container instead of per
        # shell: a long-running container stays on the build it started with,
        # and the next one gets the newer.
        [ -n "$marker" ] && [ -f "$marker" ] && return 0
        if "_${pkg}_install_latest"; then
            _flagos_clear_failed "$pkg"
            echo "${pkg} latest: $("_${pkg}_installed_version") active" >&2
            return 0
        fi
        _flagos_mark_failed "$pkg" "$want"
        return 1
    fi

    # An explicit version replaces whatever `latest` installed. The marker is
    # dropped explicitly rather than relied on to leave with the replaced tree:
    # the rest of the container must not trust a record for a build that is gone.
    "_${pkg}_satisfied" "$want" && return 0
    if "_${pkg}_install_exact" "$want"; then
        _flagos_clear_failed "$pkg"
        [ -n "$marker" ] && rm -f "$marker"
        echo "${pkg} ${want}: active" >&2
        return 0
    fi
    _flagos_mark_failed "$pkg" "$want"
    return 1
}

_compiler_import_triton() {
    # Import triton with the given dir first on PYTHONPATH, the other side dir
    # stripped first: leaving both on PYTHONPATH makes entry-point discovery
    # import every declared backend against whichever tree wins package
    # resolution, which fails when that backend exists in only one of them.
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
                _flagos_ensure flagtree "$2" force || return 1
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

# FLAGTREE_VERSION / FLAGGEMS_VERSION, when set, are version requests made at
# container start. The flag rather than an immediate exit keeps a second
# request's reason from being masked by the first one's. FlagTree first: it is
# the compiler, and without it FlagGems cannot be imported at all.
_flagos_request_failed=0
if ! _flagos_ensure flagtree "${FLAGTREE_VERSION:-}"; then
    _flagos_report_cannot_install flagtree "${FLAGTREE_VERSION:-}"
    _flagos_request_failed=1
fi
if ! _flagos_ensure flaggems "${FLAGGEMS_VERSION:-}"; then
    _flagos_report_cannot_install flaggems "${FLAGGEMS_VERSION:-}"
    _flagos_request_failed=1
fi
[ "$_flagos_request_failed" -eq 0 ] || exit 1

# Keep the default compiler active in every new shell.
if ! _compiler_active_dir >/dev/null; then
    if [ -d /opt/flagtree/triton ]; then
        export PYTHONPATH="/opt/flagtree${PYTHONPATH:+:}${PYTHONPATH:-}"
    elif [ -d /opt/triton/triton ]; then
        export PYTHONPATH="/opt/triton${PYTHONPATH:+:}${PYTHONPATH:-}"
    fi
fi
