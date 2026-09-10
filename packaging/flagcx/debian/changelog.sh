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
#
# Generate debian/changelog from the FlagCX clone's own tags.
#
# The source is a fresh clone, so there is no committed changelog to keep in
# sync and no staleness gate to write. Run from the top of the clone.
#
# Version mapping — the point of the whole thing is that `~` sorts *below* the
# empty string in Debian version comparison, so a pre-release can be superseded
# by its own release (the old flow's `0.13.0-rc0.1-1` sorted above `0.13.0`):
#
#   vX.Y.Z                  -> X.Y.Z-1
#   vX.Y.Z-rcN[.M][.postP]  -> X.Y.Z~rcN[.M][.postP]-1
#
# Anything else exits non-zero rather than guessing.

set -euo pipefail

PKG="${1:?usage: changelog.sh <package> [output]}"
OUT="${2:-debian/changelog}"
MAINT='FlagOS Contributors <flagos@baai.ac.cn>'
VER_RE='^[0-9]+\.[0-9]+\.[0-9]+(~[0-9A-Za-z.+]+)?-1$'

deb_version() {
    local tag="${1#v}"
    if [[ "$tag" == *-* ]]; then
        printf '%s~%s-1\n' "${tag%%-*}" "${tag#*-}"
    else
        printf '%s-1\n' "$tag"
    fi
}

mapfile -t tags < <(git tag --sort=-creatordate)
if [[ ${#tags[@]} -eq 0 ]]; then
    echo "changelog.sh: $(pwd) has no tags — clone without --depth" >&2
    exit 1
fi

: > "$OUT"
for i in "${!tags[@]}"; do
    tag="${tags[i]}"
    ver="$(deb_version "$tag")"
    if [[ ! "$ver" =~ $VER_RE ]]; then
        echo "changelog.sh: tag $tag does not map to a Debian version (got $ver)" >&2
        exit 1
    fi
    # Each entry covers the commits since the next-older tag; the oldest tag
    # gets its reachable history, which is what it introduced.
    if (( i + 1 < ${#tags[@]} )); then
        range="${tags[i + 1]}..$tag"
    else
        range="$tag"
    fi
    {
        printf '%s (%s) unstable; urgency=medium\n\n' "$PKG" "$ver"
        # -n, not `| head -50`: the oldest tag reaches the whole history, and a
        # SIGPIPE from head would trip pipefail and truncate the entry *before*
        # its trailer line.
        git log -n 50 --no-merges --format='  * %s' "$range"
        printf '\n -- %s  %s\n\n' "$MAINT" "$(git log -1 --format=%aD "$tag")"
    } >> "$OUT"
done
