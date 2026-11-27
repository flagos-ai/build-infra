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

# Verify installed DEB or RPM shared libraries inside a clean target container:
#   1. Undeclared dependencies provided by installed system packages fail.
#   2. Public libraries missing RUNPATH to package-private dependencies fail.
#   3. Undefined non-Python symbols fail unless satisfied by a governing
#      dlopen plugin host in the same package.
set -euo pipefail

FORMAT=""
PKG_DIR="/pkg"
CHECKED=0
ENV_MISSING_COUNT=0
PKG_SOS=()
PKG_DIRS=""
LOADABLE_HOSTS=()
UNPRELOAD_HOSTS=()

# Return 0 when a directory is searched by the dynamic loader by default.
is_public_dir() {
    case "$1" in
        /lib|/lib64|/usr/lib|/usr/lib64) return 0 ;;
        /lib/*-linux-gnu*|/usr/lib/*-linux-gnu*)
            local sub="${1#/usr}"
            sub="${sub#/lib/}"
            case "$sub" in */*) return 1 ;; *) return 0 ;; esac ;;
        *) return 1 ;;
    esac
}

# Return 0 when a dlopen host directory can legitimately load a plugin directory.
host_governs_plugin() {
    local host_dir="$1" plugin_dir="$2"
    is_public_dir "$host_dir" && return 0
    case "$plugin_dir/" in "$host_dir/"*) return 0 ;; esac
    local hp hb
    hp="$(dirname "$host_dir")"
    hb="$(basename "$host_dir")"
    case "$hb:$plugin_dir/" in _C:"$hp/"*|lib:"$hp/"*) return 0 ;; esac
    return 1
}

# List package names produced by the staged binary artifacts.
list_pkg_names() {
    if [ "$FORMAT" = "deb" ]; then
        local d
        for d in "$PKG_DIR"/*.deb; do
            [ -f "$d" ] && dpkg-deb -f "$d" Package
        done
    else
        rpm -qp --qf "%{NAME}\n" "$PKG_DIR"/*.rpm | sort -u
    fi
}

# Populate PKG_SOS and colon-joined PKG_DIRS for one installed package.
collect_pkg_sos() {
    local pkg="$1" line
    PKG_SOS=()
    local raw_list
    if [ "$FORMAT" = "deb" ]; then
        raw_list="$(dpkg -L "$pkg" | grep -E '\.so($|\.)' || true)"
    else
        raw_list="$(rpm -ql "$pkg" | grep -E '\.so($|\.)' || true)"
    fi
    while IFS= read -r line; do
        [ -n "$line" ] && [ -f "$line" ] && PKG_SOS+=("$line")
    done <<< "$raw_list"

    if [ "${#PKG_SOS[@]}" -eq 0 ]; then
        PKG_DIRS=""
        return 0
    fi
    PKG_DIRS="$(printf '%s\n' "${PKG_SOS[@]}" | sed -E 's|/[^/]+$||' | sort -u | paste -sd: -)"
}

# Query the installed package that owns a resolved ELF file path.
file_owner() {
    local real_so="$1"
    if [ "$FORMAT" = "deb" ]; then
        dpkg -S "$real_so" | head -1 | cut -d: -f1
    else
        rpm -qf "$real_so" --qf "%{NAME}\n" | head -1
    fi
}

# Find which installed package provides a missing SONAME, if any.
find_lib_provider() {
    local lib="$1"
    if [ "$FORMAT" = "deb" ]; then
        dpkg -S "*/$lib" 2>/dev/null | head -1 | cut -d: -f1 || true
        return 0
    fi
    local provider
    provider="$(rpm -q --whatprovides "${lib}()(64bit)" --qf "%{NAME}\n" 2>/dev/null | head -1 || true)"
    case "$provider" in
        ""|*"no package provides"*) ;;
        *) printf '%s\n' "$provider"; return 0 ;;
    esac
    local d cand_files=()
    IFS=':' read -r -a _dirs <<< "$PKG_DIRS"
    for d in "${_dirs[@]}"; do
        [ -n "$d" ] && [ -e "$d/$lib" ] && cand_files+=("$d/$lib")
    done
    if [ "${#cand_files[@]}" -gt 0 ]; then
        provider="$(rpm -qf "${cand_files[@]}" --qf "%{NAME}\n" 2>/dev/null | head -1 || true)"
        case "$provider" in
            ""|*"no package provides"*) ;;
            *) printf '%s\n' "$provider" ;;
        esac
    fi
}

# Return 0 when owner declares a dependency on provider (or SONAME in RPM).
owner_declares_dep() {
    local owner="$1" provider="$2" lib="$3" declared
    if [ "$FORMAT" = "deb" ]; then
        declared="$(dpkg-query -W -f='${Depends}' "$owner" | tr ',|' '\n\n' | sed -E 's/^ +//; s/[ (:].*//' || true)"
        printf '%s\n' "$declared" | grep -x "$provider" >/dev/null
    else
        declared="$(rpm -q --requires "$owner" 2>/dev/null || true)"
        printf '%s\n' "$declared" | grep -E "^(${provider}($|[ (])|${lib}[(][)])" >/dev/null
    fi
}

# Print matching package-owned library paths for one direct DT_NEEDED soname.
match_pkg_soname() {
    local soname="$1" cand
    for cand in "${PKG_SOS[@]}"; do
        [ "$(basename "$cand")" = "$soname" ] && printf '%s\n' "$cand"
    done
    return 0
}

# Collect direct package-owned DT_NEEDED library paths for a single ELF binary.
direct_needed_paths() {
    local elf="$1" soname
    while IFS= read -r soname; do
        [ -n "$soname" ] && match_pkg_soname "$soname"
    done < <(readelf -d "$elf" 2>/dev/null | grep "(NEEDED)" | sed -E 's/.*\[([^]]+)\].*/\1/' || true)
}

# Breadth-first search of package-internal directories needed by an ELF binary.
needed_dirs_for() {
    local queue=("$1") seen=" " dirs="" cur match cdir
    while [ "${#queue[@]}" -gt 0 ]; do
        cur="${queue[0]}"
        queue=("${queue[@]:1}")
        case "$seen" in *" $cur "*) continue ;; esac
        seen="${seen}${cur} "
        while IFS= read -r match; do
            [ -n "$match" ] || continue
            cdir="$(dirname "$(readlink -f "$match")")"
            dirs="${dirs:+$dirs:}$cdir"
            queue+=("$match")
        done < <(direct_needed_paths "$cur")
    done
    printf '%s' "$dirs"
}

# Classify package libraries that import dlopen into preloadable vs unpreloadable hosts.
classify_hosts() {
    LOADABLE_HOSTS=()
    UNPRELOAD_HOSTS=()
    local h h_dirs undef_syms ldd_h ldd_r_h
    for h in "${PKG_SOS[@]}"; do
        case "$(basename "$h")" in *.cpython-*.so) continue ;; esac
        undef_syms="$(nm -D -u "$h" 2>/dev/null | awk '{print $NF}' | sed 's/@.*//' || true)"
        printf '%s\n' "$undef_syms" | grep -x "dlopen" >/dev/null || continue
        h_dirs="$(needed_dirs_for "$h")"
        ldd_h="$(LD_LIBRARY_PATH="$h_dirs" ldd "$h" 2>&1 || true)"
        ldd_r_h="$(LD_LIBRARY_PATH="$h_dirs" ldd -r "$h" 2>&1 || true)"
        if ! printf '%s\n' "$ldd_h" | grep "=> not found" >/dev/null \
           && ! printf '%s\n' "$ldd_h" | grep -E "version .* not found" >/dev/null \
           && ! printf '%s\n' "$ldd_r_h" | grep -vE "undefined symbol: _?Py" | grep "undefined symbol" >/dev/null; then
            LOADABLE_HOSTS+=("$h")
        else
            UNPRELOAD_HOSTS+=("$h")
        fi
    done
}

# Inspect one missing SONAME reported by ldd for an ELF object.
inspect_missing_lib() {
    local so="$1" owner="$2" is_public="$3" lib="$4" provider
    provider="$(find_lib_provider "$lib")"
    if [ "$provider" = "$owner" ]; then
        if [ "$is_public" -eq 1 ]; then
            echo "$(basename "$so"): $lib is shipped by $owner outside the loader path, and $(basename "$so") has no RUNPATH to reach it"
            exit 1
        fi
        echo "  $(basename "$so"): $lib shipped by the package itself"
        return 0
    fi
    if [ -n "$provider" ] && ! owner_declares_dep "$owner" "$provider" "$lib"; then
        echo "$(basename "$so"): $lib is provided by an installed package ($provider) but not declared"
        exit 1
    fi
    echo "  $(basename "$so"): $lib left to the environment"
    ENV_MISSING_COUNT=$((ENV_MISSING_COUNT + 1))
}

# Check symbol-version compatibility and missing SONAMEs reported by ldd.
check_missing_libs() {
    local so="$1" owner="$2" is_public="$3" ldd_out ver_err lib
    ENV_MISSING_COUNT=0
    ldd_out="$(ldd "$so" 2>&1 || true)"
    ver_err="$(printf '%s\n' "$ldd_out" | grep -E "version .* not found" || true)"
    if [ -n "$ver_err" ]; then
        echo "$(basename "$so") has symbol version mismatch:"
        printf '%s\n' "$ver_err" | head -5
        exit 1
    fi
    while IFS= read -r lib; do
        [ -n "$lib" ] && inspect_missing_lib "$so" "$owner" "$is_public" "$lib"
    done < <(printf '%s\n' "$ldd_out" | awk '/=> not found/ {print $1}')
}

# Verify symbol relocations for a public shared library.
check_public_symbols() {
    local so="$1" undefined
    undefined="$(ldd -r "$so" 2>&1 | grep "undefined symbol" | grep -vE "undefined symbol: _?Py" | awk '{print $3}' || true)"
    if [ -n "$undefined" ]; then
        echo "$(basename "$so") has undefined symbols:"
        printf '%s\n' "$undefined" | head -5
        exit 1
    fi
    echo "  $(basename "$so"): links resolve"
}

# Write symbols exported by governing hosts that cannot be LD_PRELOADed to a file.
write_unpreload_host_symbols() {
    local real_so="$1" so_dir="$2" out_file="$3" h h_real
    : > "$out_file"
    for h in "${UNPRELOAD_HOSTS[@]}"; do
        h_real="$(readlink -f "$h")"
        [ "$h_real" = "$real_so" ] && continue
        host_governs_plugin "$(dirname "$h_real")" "$so_dir" || continue
        nm -D --defined-only "$h" 2>/dev/null | awk '{print $NF}' | sed 's/@.*//' >> "$out_file"
    done
    sort -u -o "$out_file" "$out_file"
}

# Run ldd -r with optional LD_PRELOAD and filter expected interpreter/host symbols.
unresolved_symbols_under() {
    local preload="$1" lib_path="$2" so="$3" sym_file="$4"
    local raw
    if [ -n "$preload" ]; then
        raw="$(LD_PRELOAD="$preload" LD_LIBRARY_PATH="$lib_path" ldd -r "$so" 2>&1 || true)"
    else
        raw="$(LD_LIBRARY_PATH="$lib_path" ldd -r "$so" 2>&1 || true)"
    fi
    printf '%s\n' "$raw" \
        | grep "undefined symbol" \
        | grep -vE "undefined symbol: _?Py" \
        | awk '{print $3}' \
        | grep -vxF -f "$sym_file" || true
}

# Verify symbol relocations for a private library or dlopen plugin.
check_private_symbols() {
    local so="$1" real_so="$2" so_dir="$3"
    local so_dirs sym_file="/tmp/defined-unpreload-$$"
    so_dirs="$(needed_dirs_for "$so")"
    write_unpreload_host_symbols "$real_so" "$so_dir" "$sym_file"

    local gov_hosts=() h h_real
    for h in "${LOADABLE_HOSTS[@]}"; do
        h_real="$(readlink -f "$h")"
        [ "$h_real" = "$real_so" ] && continue
        host_governs_plugin "$(dirname "$h_real")" "$so_dir" && gov_hosts+=("$h")
    done

    local resolved=0 undefined="" hd try_dirs cand_undef
    if [ "${#gov_hosts[@]}" -gt 0 ]; then
        for h in "${gov_hosts[@]}"; do
            hd="$(needed_dirs_for "$h")"
            try_dirs="${so_dirs}${hd:+:${hd}}"
            try_dirs="${try_dirs#:}"
            cand_undef="$(unresolved_symbols_under "$h" "$try_dirs" "$so" "$sym_file")"
            if [ -z "$cand_undef" ]; then
                resolved=1
                undefined=""
                break
            fi
            undefined="$cand_undef"
        done
    else
        undefined="$(unresolved_symbols_under "" "$so_dirs" "$so" "$sym_file")"
        [ -z "$undefined" ] && resolved=1
    fi
    rm -f "$sym_file"

    if [ "$resolved" -eq 0 ]; then
        echo "$(basename "$so") has undefined symbols:"
        printf '%s\n' "$undefined" | head -5
        exit 1
    fi
    echo "  $(basename "$so"): links resolve"
}

# Verify one shared object shipped by an installed package.
verify_one_so() {
    local so="$1" real_so so_dir is_public=0 owner
    CHECKED=$((CHECKED + 1))
    real_so="$(readlink -f "$so")"
    so_dir="$(dirname "$real_so")"
    is_public_dir "$so_dir" && is_public=1
    owner="$(file_owner "$real_so")"

    check_missing_libs "$so" "$owner" "$is_public"
    if [ "$ENV_MISSING_COUNT" -gt 0 ]; then
        echo "  $(basename "$so"): $ENV_MISSING_COUNT left to the environment, symbols not checked"
    elif [ "$is_public" -eq 1 ]; then
        check_public_symbols "$so"
    else
        check_private_symbols "$so" "$real_so" "$so_dir"
    fi
}

main() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --format) FORMAT="$2"; shift 2 ;;
            *) PKG_DIR="$1"; shift ;;
        esac
    done
    case "$FORMAT" in
        deb|rpm) ;;
        *) echo "Usage: $0 --format deb|rpm [pkg_dir]" >&2; exit 2 ;;
    esac

    local pkg so
    while IFS= read -r pkg; do
        [ -n "$pkg" ] || continue
        collect_pkg_sos "$pkg"
        [ "${#PKG_SOS[@]}" -gt 0 ] || continue
        classify_hosts
        for so in "${PKG_SOS[@]}"; do
            verify_one_so "$so"
        done
    done < <(list_pkg_names)

    [ "$CHECKED" -gt 0 ] || { echo "no shared library shipped"; exit 1; }
    echo "OK: $CHECKED shared librar(y|ies) checked, nothing undeclared"
}

main "$@"
