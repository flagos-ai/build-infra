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

# ============================================================================
# verify_bundle.sh — install + closure equality + smoke test, with NO network.
#
#   verify_bundle.sh <tarball> [--app-version 0.24.0]
#
#   1. Closure equality: bundle wheelhouse == the wheels the runtime + app
#      images install, derived from configs.yaml + app-versions.yaml (same
#      resolver the build uses).
#   2. Install: run install.sh inside a `--network none` container (egress
#      denied at the docker layer, not merely unobserved).
#   3. Smoke test, same container (the venv references the standalone CPython
#      staged in $HOME, so install + smoke must share one container): import
#      the app's smoke modules, run scripts/bundle/smoke.py (device +
#      compiler JIT/execute probe), toggle `compiler`, run
#      `<launcher> --help`.
#
# The smoke container mounts the NVIDIA driver (torch+cu128 bundles the CUDA
# runtime) via .github/build-config.yml run.vendors.nvidia.raw, exactly as a
# bare-metal host would expose it.
#
# The container is ubuntu:22.04 because that is the bundle's glibc floor: the
# nvidia flagcx wheel is built self-contained on 22.04 (#1372), so it links at
# most glibc 2.35, and the smoke running at the floor is what proves a
# 22.04 host can install and import it. It was briefly pinned to 24.04 while
# the wheels were still 24.04-built (5eb9ce02); the floor test is the point,
# not the matching.
# ============================================================================

set -euo pipefail

TARBALL="${1:-}"
shift || true
APP_VERSION=""
while [ $# -gt 0 ]; do
    case "$1" in
        --app-version) APP_VERSION="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

[ -n "$TARBALL" ] || { echo "usage: $0 <bundle.tar.gz> [--app-version <ver>]" >&2; exit 2; }
[ -f "$TARBALL" ] || { echo "error: $TARBALL not found" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_NAME="$(basename "$TARBALL" .tar.gz)"
WORK_DIR="$(mktemp -d)"
# The venv is built with `uv venv --relocatable`, which (via the managed
# CPython in $HOME) materializes files as read-only; a plain `rm -rf` of the
# prefix would chmod them but still cannot unlink them as non-root. chmod -R
# u+w first so the cleanup trap can always remove the dir, root or not.
# Each command is `|| true`-guarded: under `set -e`, a command in the EXIT
# trap that fails — even one silenced with 2>/dev/null, e.g. chmod on a
# root-owned file left by the smoke container — overrides the script's exit
# status, turning a green "verify passed" into a step failure (and, before
# the artifact step was failure-gated, a 4 GB re-upload).
trap 'chmod -R u+w "$WORK_DIR" 2>/dev/null || true; rm -rf "$WORK_DIR" || true' EXIT

# ── 1. Closure equality ─────────────────────────────────────────────────────
echo "==> closure equality: wheelhouse vs images (configs.yaml + app-versions.yaml)"
python3 "$REPO_ROOT/scripts/verify_bundle.py" "$TARBALL" --check-wheels

# ── 2 + 3. Install + smoke test, one network-denied container ──────────────
echo "==> install + smoke test under --network none"
mkdir -p "$WORK_DIR/bundle" "$WORK_DIR/prefix"
tar xzf "$TARBALL" -C "$WORK_DIR/bundle"
cp "$REPO_ROOT/scripts/bundle/smoke.py" "$WORK_DIR/smoke.py"

# The install runs as root in the container, so the standalone CPython lands in
# /root/.local/share/uv/python and the venv references it — which is why
# install and smoke share ONE container below.
cat > "$WORK_DIR/smoke.sh" <<'SMOKE'
set -euo pipefail
cd "/verify/bundle/${BUNDLE_NAME}"

# We run as root in this container; the prefix install.sh creates is root-
# owned on the host, so the host-side cleanup trap (non-root) cannot unlink
# it. Remove it here in an EXIT trap so it fires on the failure path too —
# without it a failed smoke leaks a multi-GB root-owned venv per run.
trap 'rm -rf /verify/prefix 2>/dev/null || true' EXIT

# meta.env (written by build_bundle.py) tells us the launcher to smoke-test.
LAUNCHER="$(sed -n 's/^LAUNCHER=//p' meta.env)"
[ -n "$LAUNCHER" ] || LAUNCHER="${BUNDLE_NAME%-*}" # fallback: never expected

./install.sh --prefix /verify/prefix --app-version "${APP_VERSION}"

PREFIX="/verify/prefix"
# Source the full profile.d env (runtime vendor LD_LIBRARY_PATH + app env +
# compiler), exactly as the launcher and every real shell would — torch needs
# the vendor runtime libs for the device probe, not just the compiler path.
for f in "$PREFIX"/etc/profile.d/*.sh; do [ -r "$f" ] && . "$f"; done

echo "==> compiler toggle"
"$PREFIX/bin/compiler" triton
"$PREFIX/bin/compiler" flagtree

echo "==> deep smoke (device + compiler JIT/execute) — flagtree active"
"$PREFIX/bin/python" /verify/smoke.py

if [ -x "$PREFIX/bin/$LAUNCHER" ]; then
    echo "==> $LAUNCHER --help"
    "$PREFIX/bin/$LAUNCHER" --help >/dev/null && echo "$LAUNCHER --help OK"
fi

# Remove our own prefix before exiting: install.sh ran as root in this
# container, so these files are root-owned on the host and the host-side
# cleanup trap (non-root) cannot unlink them. Doing it here on the success
# path (the EXIT trap above also covers the failure path) leaves just
# host-owned files for the host trap.
rm -rf /verify/prefix

echo "==> verify passed"
SMOKE
sed -i "s/\${BUNDLE_NAME}/${BUNDLE_NAME}/g; s/\${APP_VERSION}/${APP_VERSION:-0.24.0}/g" "$WORK_DIR/smoke.sh"
# The here-doc was quoted, so the sed above filled the two tokens literally.

# Mount the NVIDIA driver (raw device passthrough, as a bare-metal host would)
# so torch can see the GPU; --network none denies all egress.
docker run --rm --network none \
    -v "$WORK_DIR":/verify \
    --device /dev/nvidia0 --device /dev/nvidiactl --device /dev/nvidia-uvm \
    -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
    -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
    -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
    ubuntu:22.04 bash /verify/smoke.sh

echo "==> verify passed: bundle installs and imports with the network denied"
