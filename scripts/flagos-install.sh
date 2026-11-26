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

set -eu

BASE=${FLAGOS_REPO_BASE:-https://resource.flagos.net/repository}
KEY_URL=${FLAGOS_KEY_URL:-$BASE/apt-keys/pub/flagos-apt-public-key.asc}
KEY_FPR=C487A636179B0780A77E3B65CA80C6CA3E9AE441
KEYRING=/etc/apt/keyrings/flagos.asc

KNOWN_VENDORS='nvidia ascend ascend-910c metax amd enflame ppu thead tileir hygon hcu du mthreads musa tsingmicro tsm kunlunxin xpu klx cambricon iluvatar iluvatar-corex sunrise cpu'

# pkg|published suites|staged suites (probed silently once published)|arches|vendor class
CATALOG='
python3-flag-gems|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03||all|common
python3-flag-audio|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03||all|common
python3-flag-attention|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03||all|common
python3-flag-blas|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03||all|common
python3-flagsparse|ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03||all|common
python3-flaggems-sglang||ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03|all|common
python3-flagtensor|ubuntu24.04 rhel9|ubuntu22.04 fedora43 openeuler24.03|all|common
libflagtensor-nvidia|ubuntu24.04 rhel9|ubuntu22.04 fedora43 openeuler24.03|x86_64|nvidia
python3-flagtensor-nvidia|ubuntu24.04 rhel9|ubuntu22.04 fedora43 openeuler24.03|x86_64|nvidia
libflagdnn-nvidia|ubuntu24.04 rhel9|ubuntu22.04 fedora43 openeuler24.03|x86_64|nvidia
libflagfft-nvidia|ubuntu22.04|ubuntu24.04 openeuler24.03|x86_64|nvidia
python3-flagtree-nvidia|ubuntu24.04 fedora43 openeuler24.03||x86_64|nvidia
python3-flagtree-ascend|openeuler24.03||aarch64|ascend
python3-flagtree-metax||ubuntu24.04|x86_64|metax
python3-flagtree-amd||ubuntu24.04|x86_64|amd
python3-flagtree-enflame||ubuntu24.04|x86_64|enflame
python3-flagtree-ppu||ubuntu24.04|x86_64|ppu
python3-flagtree-tileir||ubuntu24.04|x86_64|tileir
python3-flagtree-hcu||ubuntu22.04|x86_64|hcu
python3-flagtree-mthreads||ubuntu22.04|x86_64|mthreads
python3-flagtree-tsingmicro||ubuntu22.04|x86_64|tsingmicro
python3-flagtree-xpu||ubuntu22.04|x86_64|xpu
python3-flagtree-cpu||ubuntu22.04 ubuntu24.04 fedora43 openeuler24.03|x86_64 aarch64|cpu
libtriton-jit-nvidia|ubuntu24.04 rhel9|ubuntu22.04 fedora43 openeuler24.03|x86_64|nvidia
'

# pkg|suites it is broken on|why
CAVEATS='
python3-flag-audio|openeuler24.03|requires python3.11dist(pybind11), which pulls in pybind11-devel and cmake from everything (FlagAudio#26)
python3-flag-blas|openeuler24.03|requires python3.11dist(pybind11), which pulls in pybind11-devel and cmake from everything (FlagBLAS#144)
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
  --vendor VENDOR   install common packages plus native + FlagCX packages for VENDOR
                    (e.g. nvidia, ascend, metax, amd, mthreads, hcu, xpu, cpu)
  --component NAME  install only this package (repeatable)
  --flagcx VENDOR   also install the FlagCX build for VENDOR (e.g. nvidia, ascend)
  --print-steps     print the equivalent manual commands instead of running them
  --force           install packages this script would skip (see CAVEATS)
  --dry-run         print the install command instead of running it
  --yes             do not ask for confirmation
EOF
}

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

detect_arch() {
  raw_arch=${FLAGOS_ARCH:-$(uname -m)}
  case "$raw_arch" in
    x86_64|amd64)  ARCH=x86_64 ;;
    aarch64|arm64) ARCH=aarch64 ;;
    *)             ARCH=$raw_arch ;;
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

canonical_catalog_vendor() {
  case "$1" in
    ascend-910c)             echo ascend ;;
    hygon|hcu|du)            echo hcu ;;
    kunlunxin|xpu|klx)       echo xpu ;;
    tsingmicro|tsm)          echo tsingmicro ;;
    mthreads|musa)           echo mthreads ;;
    ppu|thead)               echo ppu ;;
    iluvatar|iluvatar-corex) echo iluvatar ;;
    *)                       echo "$1" ;;
  esac
}

pypi_vendor_name() {
  case "$1" in
    ascend|ascend-910c)      echo ascend ;;
    hygon|hcu|du)            echo hygon ;;
    kunlunxin|xpu|klx)       echo kunlunxin ;;
    tsingmicro|tsm)          echo tsingmicro ;;
    mthreads|musa)           echo mthreads ;;
    ppu|thead)               echo thead ;;
    iluvatar|iluvatar-corex) echo iluvatar ;;
    *)                       echo "$1" ;;
  esac
}

# Emit pkg|mode (mode = published | staged) filtered by SUITE, ARCH, and optional VENDOR.
catalog_candidates() {
  want_vclass=''
  [ -n "$VENDOR" ] && want_vclass=$(canonical_catalog_vendor "$VENDOR")
  printf '%s\n' "$CATALOG" | while IFS= read -r line; do
    [ -n "$line" ] || continue
    pkg=$(field "$line" 1)
    pub_suites=$(field "$line" 2)
    stg_suites=$(field "$line" 3)
    arches=$(field "$line" 4)
    vclass=$(field "$line" 5)
    if [ "$arches" != all ] && ! in_list "$ARCH" "$arches"; then
      continue
    fi
    if [ -n "$want_vclass" ] && [ "$vclass" != common ] && [ "$vclass" != "$want_vclass" ]; then
      continue
    fi
    if in_list "$SUITE" "$pub_suites"; then
      printf '%s|published\n' "$pkg"
    elif in_list "$SUITE" "$stg_suites"; then
      printf '%s|staged\n' "$pkg"
    fi
  done
}

configure_deb() {
  command -v curl >/dev/null || die "curl is required; apt-get install -y curl ca-certificates"
  install -d -m 0755 "$(dirname "$KEYRING")"
  tmp=$(mktemp)
  curl -fsSL "$KEY_URL" -o "$tmp" || die "cannot fetch the repository key from $KEY_URL"
  if command -v gpg >/dev/null; then
    got=$(gpg --show-keys --with-colons "$tmp" | awk -F: '$1=="fpr"{print $10; exit}')
    [ "$got" = "$KEY_FPR" ] || die "repository key fingerprint is $got, expected $KEY_FPR"
  else
    warn "gpg not installed; cannot check the key fingerprint (expected $KEY_FPR)"
  fi
  install -m 0644 "$tmp" "$KEYRING"
  rm -f "$tmp"
  printf 'deb [signed-by=%s] %s/flagos-apt-%s %s main\n' \
    "$KEYRING" "$BASE" "$SUITE" "$CODENAME" > /etc/apt/sources.list.d/flagos.list
  say "configured /etc/apt/sources.list.d/flagos.list (signed-by $KEYRING)"
  apt-get update -qq
}

configure_rpm() {
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

repo_has() {
  case $FAMILY in
    deb) apt-cache policy "${1%%:*}" 2>/dev/null | grep -Fq "/flagos-apt-$SUITE" ;;
    rpm) $DNF -q --disablerepo='*' --enablerepo=flagos list --available "$1" >/dev/null 2>&1 ;;
  esac
}

flagcx_package() {
  # FlagCX names its virtual Provides (on deb) and binary packages (on rpm)
  # after the adaptor family (du, tsm, musa, klx, iluvatar-corex, ppu), while
  # DEB package prefixes follow the vendor/SDK key (hygon-dtk*, thead-ppu*,
  # iluvatar-corex*, kunlunxin-xre*, mthreads-musa*, tsingmicro-tsm*).
  adaptor=$1
  deb_re="^libflagcx-${1}($|-)"
  rpm_globs="libflagcx-${1}*"
  case "$1" in
    hygon|hcu|du)
      adaptor=du
      deb_re='^libflagcx-(hygon|du)($|-)'
      rpm_globs='libflagcx-du* libflagcx-hygon*' ;;
    tsingmicro|tsm)
      adaptor=tsm
      deb_re='^libflagcx-(tsingmicro|tsm)($|-)'
      rpm_globs='libflagcx-tsm* libflagcx-tsingmicro*' ;;
    mthreads|musa)
      adaptor=musa
      deb_re='^libflagcx-(mthreads|musa)($|-)'
      rpm_globs='libflagcx-musa* libflagcx-mthreads*' ;;
    iluvatar|iluvatar-corex|iluvatar_corex)
      adaptor=iluvatar-corex
      deb_re='^libflagcx-(iluvatar-corex|iluvatar)($|[-0-9])'
      rpm_globs='libflagcx-iluvatar-corex* libflagcx-iluvatar*' ;;
    kunlunxin|xpu|klx)
      adaptor=klx
      deb_re='^libflagcx-(kunlunxin|klx)($|-)'
      rpm_globs='libflagcx-klx* libflagcx-kunlunxin*' ;;
    ppu|thead)
      adaptor=ppu
      deb_re='^libflagcx-(thead-ppu|ppu)($|[-0-9])'
      rpm_globs='libflagcx-ppu* libflagcx-thead*' ;;
    ascend-910c)
      adaptor=''
      deb_re='^libflagcx-ascend($|-)'
      rpm_globs='libflagcx-ascend*' ;;
  esac
  target="libflagcx-${adaptor}"
  case $FAMILY in
    deb)
      if [ -n "$adaptor" ] && repo_has "$target"; then
        printf '%s\n' "$target"
        return 0
      fi
      if [ -n "$adaptor" ]; then
        prov=$(apt-cache showpkg "$target" 2>/dev/null \
               | awk '/^Reverse Provides:/{p=1; next} p && NF{print $1}' \
               | grep -vE -- '-(dev|dbgsym)$' | sort -V | tail -n 1 || true)
        if [ -n "$prov" ]; then
          printf '%s\n' "$prov"
          return 0
        fi
      fi
      cands=$(apt-cache search --names-only "$deb_re" 2>/dev/null \
              | awk '{print $1}' | grep -vE -- '-(dev|dbgsym)$' || true)
      case "$1" in
        *-910c) printf '%s\n' "$cands" | grep -- '-910c$' | sort -V | tail -n 1 || true ;;
        *)      non910=$(printf '%s\n' "$cands" | grep -v -- '-910c$' || true)
                printf '%s\n' "${non910:-$cands}" | sort -V | tail -n 1 ;;
      esac
      ;;
    rpm)
      # Strip only the trailing .<arch> token so dotted SDK versions such as
      # libflagcx-ascend-cann9.0.0.aarch64 are preserved intact.
      cands=''
      for g in $rpm_globs; do
        part=$($DNF -q --disablerepo='*' --enablerepo=flagos list --available "$g" 2>/dev/null \
               | awk '/^libflagcx/{sub(/\.[^.]+$/, "", $1); print $1}' \
               | grep -vE -- '-(devel|debuginfo|debugsource)$' || true)
        [ -n "$part" ] && cands=$(printf '%s\n%s\n' "$cands" "$part" | awk 'NF' | sort -u)
      done
      if [ -n "$adaptor" ] && printf '%s\n' "$cands" | grep -qx "$target"; then
        printf '%s\n' "$target"
      else
        case "$1" in
          *-910c) printf '%s\n' "$cands" | grep -- '-910c$' | sort -V | tail -n 1 || true ;;
          *)      non910=$(printf '%s\n' "$cands" | grep -v -- '-910c$' || true)
                  printf '%s\n' "${non910:-$cands}" | sort -V | tail -n 1 ;;
        esac
      fi
      ;;
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

print_torch_hint() {
  say ""
  say "note: these packages do not pull in torch. Install the ABI-matched build"
  say "      for your distribution and accelerator:"
  target_vendor=${VENDOR:-${FLAGCX:-nvidia}}
  if [ "$target_vendor" = cpu ]; then
    say "      pip install torch"
  elif [ "$target_vendor" != nvidia ]; then
    pypi_vendor=$(pypi_vendor_name "$target_vendor")
    extra_pkgs=torch
    case "$pypi_vendor" in
      ascend)    extra_pkgs='torch torch-npu' ;;
      enflame)   extra_pkgs='torch torch-gcu' ;;
      mthreads)  extra_pkgs='torch torch-musa' ;;
      cambricon) extra_pkgs='torch torch-mlu' ;;
    esac
    say "      pip install --index-url $BASE/flagos-pypi-$pypi_vendor/simple $extra_pkgs"
  else
    case $SUITE in
      ubuntu22.04|ubuntu24.04)
        say "      pip install --index-url $BASE/flagos-pypi-nvidia/simple \\"
        say "        --extra-index-url https://download.pytorch.org/whl/cu128 \\"
        say "        'torch==2.10.0+cu128' 'triton==3.6.0'" ;;
      rhel9)
        say "      pip install 'torch==2.8.0' 'triton==3.4.0'   # matches EL9 Python 3.9 native RPM ABI" ;;
      openeuler24.03)
        say "      pip install --extra-index-url https://download.pytorch.org/whl/cu128 \\"
        say "        'torch==2.8.0+cu128' 'triton==3.4.0'      # matches openEuler 24.03 Python 3.11 native RPM ABI" ;;
      fedora43)
        say "      pip install --extra-index-url https://download.pytorch.org/whl/cu128 \\"
        say "        'torch==2.9.0+cu128' 'triton==3.5.0'      # matches Fedora 43 Python 3.14 native RPM ABI" ;;
    esac
  fi
}

# --- main --------------------------------------------------------------------
WANT=''; VENDOR=''; FLAGCX=''; EXPLICIT_FLAGCX=0; LIST=0; REPO_ONLY=0; STEPS=0; FORCE=0; DRY_RUN=0; ASSUME_YES=0
while [ $# -gt 0 ]; do
  case $1 in
    --list) LIST=1 ;;
    --repo-only) REPO_ONLY=1 ;;
    --vendor)
      shift; [ $# -gt 0 ] || die "--vendor needs a name"
      in_list "$1" "$KNOWN_VENDORS" || die "unknown vendor '$1' (known: $KNOWN_VENDORS)"
      VENDOR=$1 ;;
    --component) shift; [ $# -gt 0 ] || die "--component needs a name"; WANT="$WANT $1" ;;
    --flagcx) shift; [ $# -gt 0 ] || die "--flagcx needs a vendor"; FLAGCX=$1; EXPLICIT_FLAGCX=1 ;;
    --print-steps) STEPS=1 ;;
    --force) FORCE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option $1 (--help)" ;;
  esac
  shift
done

if [ -n "$VENDOR" ] && [ "$VENDOR" != cpu ] && [ -z "$FLAGCX" ] && [ -z "$WANT" ]; then
  FLAGCX=$VENDOR
fi

detect_suite
detect_arch
say "distribution: $SUITE / $ARCH (FlagOS $FAMILY repository)"

[ "$STEPS" = 1 ] && { print_steps; exit 0; }

if [ "$FAMILY" = rpm ]; then
  DNF=$(command -v dnf5 || command -v dnf || command -v yum) || die "no dnf/yum found"
fi

[ "$(id -u)" = 0 ] || die "run as root (sudo $0 $*)"

case $FAMILY in deb) configure_deb ;; rpm) configure_rpm ;; esac
[ "$REPO_ONLY" = 1 ] && exit 0

available=''; missing=''; skipped=''
for entry in $(catalog_candidates); do
  pkg=$(field "$entry" 1)
  mode=$(field "$entry" 2)
  if ! repo_has "$pkg"; then
    [ "$mode" = published ] && missing="$missing $pkg"
    continue
  fi
  why=$(caveat_for "$pkg")
  if [ -n "$why" ] && [ "$FORCE" = 0 ]; then
    skipped="$skipped $pkg"
    warn "skipping $pkg: $why"
    continue
  fi
  [ -n "$why" ] && warn "$pkg: $why"
  available="$available $pkg"
done

if [ -n "$WANT" ]; then
  chosen=''
  for pkg in $WANT; do
    base_pkg=${pkg%%:*}
    case " $available " in
      *" $base_pkg "*) chosen="$chosen $pkg" ;;
      *)
        if repo_has "$pkg"; then
          why=$(caveat_for "$base_pkg")
          if [ -n "$why" ] && [ "$FORCE" = 0 ]; then
            die "$base_pkg is skipped on $SUITE: $why (pass --force to override)"
          fi
          [ -n "$why" ] && warn "$base_pkg: $why"
          chosen="$chosen $pkg"
        else
          die "$pkg is not available on $SUITE (run --list)"
        fi ;;
    esac
  done
  available=$chosen
fi

if [ -n "$FLAGCX" ]; then
  case " $EXPLICIT_FLAGCX:$available " in
    " 0:"*" libflagcx-"*) ;;
    *)
      fx=$(flagcx_package "$FLAGCX" || true)
      if [ -n "$fx" ]; then
        case " $available " in *" $fx "*) ;; *) available="$available $fx" ;; esac
      else
        warn "no FlagCX build for '$FLAGCX' in flagos-$([ "$FAMILY" = deb ] && echo apt || echo yum)-$SUITE"
      fi ;;
  esac
fi

# FlagTree compiles kernels on first use and needs the Python headers at run
# time; published 0.7.0 packages predate FlagTree#1382.
case " $available " in
  *" python3-flagtree-"*)
    hdr=$([ "$FAMILY" = deb ] && echo python3-dev || echo python3-devel)
    case " $available " in *" $hdr "*) ;; *) available="$available $hdr" ;; esac ;;
esac

say ""
say "available here:$([ -n "$available" ] && echo "$available" || echo ' (none)')"
[ -n "$missing" ] && say "not published for $SUITE:$missing"
[ -n "$skipped" ] && say "skipped (use --force):$skipped"

[ "$LIST" = 1 ] && exit 0
[ -n "$available" ] || die "nothing to install for $SUITE"

if [ "$ASSUME_YES" = 0 ] && [ "$DRY_RUN" = 0 ] && [ -t 0 ]; then
  printf 'install:%s\n[y/N] ' "$available"
  read -r reply
  case $reply in y|Y|yes) ;; *) say "aborted"; exit 1 ;; esac
fi

install_packages $available
say "done"
print_torch_hint
