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
#
# One command to put FlagOS on a supported distribution: detect the
# distribution, configure the matching FlagOS repository, install what that
# repository actually offers.
#
# Three things this does that `apt install` alone cannot:
#   * refuses an unrecognized distribution instead of guessing a near match --
#     the native packages link against one distribution's libraries, so a wrong
#     guess installs and then crashes, which is worse than not installing;
#   * asks the repository what it carries and reports the gaps by name, rather
#     than handing the user a dependency-resolver error;
#   * carries the known-bad cells (see CAVEATS) so a package that installs but
#     does not work is skipped or announced, not silently recommended.
#
# The component -> suite table below is the one hand-maintained part. It states
# what the release line publishes where; availability itself is read from the
# repository at run time, so the table going stale costs a line of output and
# not a wrong install.

set -eu

BASE=${FLAGOS_REPO_BASE:-https://resource.flagos.net/repository}
KEY_URL=${FLAGOS_KEY_URL:-$BASE/apt-keys/pub/flagos-apt-public-key.asc}
KEY_FPR=C487A636179B0780A77E3B65CA80C6CA3E9AE441
KEYRING=/etc/apt/keyrings/flagos.asc

# pkg|suites it is published for
CATALOG='
python3-flag-gems|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03
python3-flag-audio|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03
python3-flag-attention|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03
python3-flag-blas|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03
python3-flagsparse|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03
python3-flagtensor|ubuntu24.04 rhel9
libflagtensor-nvidia|ubuntu24.04 rhel9
libflagdnn-nvidia|ubuntu24.04 rhel9
libflagfft-nvidia|ubuntu22.04
python3-flagtree-nvidia|ubuntu24.04 fedora43 openeuler24.03 rhel9
libtriton-jit-nvidia|ubuntu24.04 rhel9
'

# pkg|suites it is broken on|why
CAVEATS='
python3-flag-audio|openeuler24.03|requires python3.11dist(pybind11), which openEuler cannot satisfy (FlagAudio#26)
python3-flag-blas|openeuler24.03|requires python3.11dist(pybind11), which openEuler cannot satisfy (FlagBLAS#144)
libtriton-jit-nvidia|ubuntu22.04 ubuntu24.04|0.1.0-3 resolves its script directory wrongly under Debian multiarch, so JIT calls crash; fixed upstream, pending 0.1.0-4
'

say()  { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
usage: flagos-install.sh [options]

  --list            show what this distribution can install, change nothing
  --repo-only       configure the repository, install nothing
  --component NAME  install only this package (repeatable)
  --flagcx VENDOR   also install the FlagCX build for VENDOR (e.g. nvidia, ascend)
  --print-steps     print the equivalent manual commands instead of running them
  --force           install packages this script would skip (see CAVEATS)
  --dry-run         print the install command instead of running it
  --yes             do not ask for confirmation
EOF
}

# --- distribution -> suite ----------------------------------------------------
# No fallback on purpose: a native package built for one distribution is not
# portable to a sibling, so an unknown ID is an error, not a guess.
detect_suite() {
  [ -r /etc/os-release ] || die "no /etc/os-release; cannot identify this distribution"
  . /etc/os-release
  case "${ID:-}:${VERSION_ID:-}" in
    ubuntu:22.04)        SUITE=ubuntu22.04;     FAMILY=deb; CODENAME=jammy ;;
    ubuntu:24.04)        SUITE=ubuntu24.04;     FAMILY=deb; CODENAME=noble ;;
    fedora:43)           SUITE=fedora43;        FAMILY=rpm ;;
    openEuler:24.03*)    SUITE=openeuler24.03;  FAMILY=rpm ;;
    rhel:9*|rocky:9*|almalinux:9*)
                         SUITE=rhel9;           FAMILY=rpm ;;
    *) die "unsupported distribution ${ID:-?} ${VERSION_ID:-?}.
FlagOS repositories exist for: Ubuntu 22.04, Ubuntu 24.04, Fedora 43,
openEuler 24.03, RHEL 9 (and rebuilds). Packages are built against one
distribution's libraries and are not portable between them." ;;
  esac
}

field() { printf '%s' "$1" | cut -d'|' -f"$2"; }

in_list() {
  needle=$1; shift
  for item in $*; do [ "$item" = "$needle" ] && return 0; done
  return 1
}

caveat_for() {
  printf '%s\n' "$CAVEATS" | while IFS= read -r line; do
    [ -n "$line" ] || continue
    [ "$(field "$line" 1)" = "$1" ] || continue
    in_list "$SUITE" "$(field "$line" 2)" && field "$line" 3
  done
}

expected_packages() {
  printf '%s\n' "$CATALOG" | while IFS= read -r line; do
    [ -n "$line" ] || continue
    in_list "$SUITE" "$(field "$line" 2)" && field "$line" 1
  done
}

# --- repository configuration ------------------------------------------------
configure_deb() {
  command -v curl >/dev/null || die "curl is required; apt-get install -y curl ca-certificates"
  install -d -m 0755 "$(dirname "$KEYRING")"
  tmp=$(mktemp)
  curl -fsSL "$KEY_URL" -o "$tmp" || die "cannot fetch the repository key from $KEY_URL"
  # Pin the key by fingerprint: fetching it over https says the server was
  # reachable, not that the key is ours.
  if command -v gpg >/dev/null; then
    got=$(gpg --show-keys --with-colons "$tmp" | awk -F: '$1=="fpr"{print $10; exit}')
    [ "$got" = "$KEY_FPR" ] || die "repository key fingerprint is $got, expected $KEY_FPR"
  else
    warn "gpg not installed; cannot check the key fingerprint (expected $KEY_FPR)"
  fi
  install -m 0644 "$tmp" "$KEYRING"
  rm -f "$tmp"
  # One file, rewritten every run: re-running must not stack up sources.
  printf 'deb [signed-by=%s] %s/flagos-apt-%s %s main\n' \
    "$KEYRING" "$BASE" "$SUITE" "$CODENAME" > /etc/apt/sources.list.d/flagos.list
  say "configured /etc/apt/sources.list.d/flagos.list (signed-by $KEYRING)"
  apt-get update -qq
}

configure_rpm() {
  # gpgcheck=0 because the yum repositories are unsigned end to end: the
  # packages carry no signature header and repomd has no detached one, and the
  # published key covers apt only (#1424). Stated here rather than hidden --
  # this flag and the gpgkey line are what change when signing lands.
  cat > /etc/yum.repos.d/flagos.repo <<EOF
[flagos]
name=FlagOS ($SUITE)
baseurl=$BASE/flagos-yum-$SUITE
enabled=1
gpgcheck=0
EOF
  say "configured /etc/yum.repos.d/flagos.repo"
  warn "the yum repositories are not signed yet (build-infra#1424), so this repository is configured with gpgcheck=0"
}

# --- what the repository actually carries -------------------------------------
repo_has() {
  case $FAMILY in
    deb) apt-cache policy "$1" 2>/dev/null | grep -q 'Candidate: [^(]' ;;
    rpm) $DNF -q --disablerepo='*' --enablerepo=flagos list --available "$1" >/dev/null 2>&1 ;;
  esac
}

flagcx_package() {
  case $FAMILY in
    deb) apt-cache search --names-only "^libflagcx-$1" 2>/dev/null | awk '{print $1; exit}' ;;
    rpm) $DNF -q --disablerepo='*' --enablerepo=flagos list --available "libflagcx-$1*" 2>/dev/null \
           | awk '/^libflagcx/{sub(/\..*/,"",$1); print $1; exit}' ;;
  esac
}

install_packages() {
  case $FAMILY in
    deb) cmd="apt-get install -y $*" ;;
    rpm) cmd="$DNF install -y $*" ;;
  esac
  if [ "${DRY_RUN:-0}" = 1 ]; then say "would run: $cmd"; return 0; fi
  say "running: $cmd"
  # shellcheck disable=SC2086
  $cmd
}

print_steps() {
  say "# equivalent manual steps for $SUITE"
  if [ "$FAMILY" = deb ]; then
    cat <<EOF
curl -fsSL $KEY_URL -o /etc/apt/keyrings/flagos.asc
gpg --show-keys --with-colons /etc/apt/keyrings/flagos.asc   # expect $KEY_FPR
echo "deb [signed-by=/etc/apt/keyrings/flagos.asc] $BASE/flagos-apt-$SUITE $CODENAME main" \\
  > /etc/apt/sources.list.d/flagos.list
apt-get update && apt-get install -y <package>
EOF
  else
    cat <<EOF
cat > /etc/yum.repos.d/flagos.repo <<'REPO'
[flagos]
name=FlagOS ($SUITE)
baseurl=$BASE/flagos-yum-$SUITE
enabled=1
gpgcheck=0
REPO
dnf install -y <package>
EOF
  fi
}

# --- main --------------------------------------------------------------------
WANT=''; FLAGCX=''; LIST=0; REPO_ONLY=0; STEPS=0; FORCE=0; DRY_RUN=0; ASSUME_YES=0
while [ $# -gt 0 ]; do
  case $1 in
    --list) LIST=1 ;;
    --repo-only) REPO_ONLY=1 ;;
    --component) shift; [ $# -gt 0 ] || die "--component needs a name"; WANT="$WANT $1" ;;
    --flagcx) shift; [ $# -gt 0 ] || die "--flagcx needs a vendor"; FLAGCX=$1 ;;
    --print-steps) STEPS=1 ;;
    --force) FORCE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option $1 (--help)" ;;
  esac
  shift
done

detect_suite
say "distribution: $SUITE (FlagOS $FAMILY repository)"

[ "$STEPS" = 1 ] && { print_steps; exit 0; }

if [ "$FAMILY" = rpm ]; then
  DNF=$(command -v dnf5 || command -v dnf || command -v yum) || die "no dnf/yum found"
fi

[ "$(id -u)" = 0 ] || die "run as root (sudo $0 $*)"

case $FAMILY in deb) configure_deb ;; rpm) configure_rpm ;; esac
[ "$REPO_ONLY" = 1 ] && exit 0

available=''; missing=''; skipped=''
for pkg in $(expected_packages); do
  if ! repo_has "$pkg"; then missing="$missing $pkg"; continue; fi
  why=$(caveat_for "$pkg")
  if [ -n "$why" ] && [ "$FORCE" = 0 ]; then
    skipped="$skipped $pkg"
    warn "skipping $pkg: $why"
    continue
  fi
  [ -n "$why" ] && warn "$pkg: $why"
  available="$available $pkg"
done

if [ -n "$FLAGCX" ]; then
  fx=$(flagcx_package "$FLAGCX" || true)
  if [ -n "$fx" ]; then available="$available $fx"
  else warn "no FlagCX build for '$FLAGCX' in flagos-$([ "$FAMILY" = deb ] && echo apt || echo yum)-$SUITE"
  fi
fi

# FlagTree compiles kernels on first use and needs the Python headers at run
# time; the package does not declare them yet (FlagTree#1382).
case " $available " in
  *" python3-flagtree-nvidia "*)
    [ "$FAMILY" = deb ] && available="$available python3-dev" || available="$available python3-devel" ;;
esac

say ""
say "available here:$([ -n "$available" ] && echo "$available" || echo ' (none)')"
[ -n "$missing" ] && say "not published for $SUITE:$missing"
[ -n "$skipped" ] && say "skipped (use --force):$skipped"

[ "$LIST" = 1 ] && exit 0
[ -n "$available" ] || die "nothing to install for $SUITE"

if [ -n "$WANT" ]; then
  chosen=''
  for pkg in $WANT; do
    case " $available " in
      *" $pkg "*) chosen="$chosen $pkg" ;;
      *) die "$pkg is not available on $SUITE (run --list)" ;;
    esac
  done
  available=$chosen
fi

if [ "$ASSUME_YES" = 0 ] && [ "$DRY_RUN" = 0 ] && [ -t 0 ]; then
  printf 'install:%s\n[y/N] ' "$available"
  read -r reply
  case $reply in y|Y|yes) ;; *) say "aborted"; exit 1 ;; esac
fi

install_packages $available
say "done"

# The deb/rpm side deliberately does not depend on torch: the distribution's
# torch is CPU-only, and the vendor builds live on the vendor pip indexes.
# Saying so here is cheaper than the import error that follows otherwise.
say ""
say "note: these packages do not pull in torch. Install the build matching your"
say "      accelerator from the vendor index, e.g."
say "      pip install --index-url $BASE/flagos-pypi-<vendor>/simple torch"
