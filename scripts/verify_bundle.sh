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
#      the app's smoke modules, toggle `compiler`, run `<launcher> --help`.
#
# The smoke container mounts the NVIDIA driver (torch+cu128 bundles the CUDA
# runtime) via .github/build-config.yml run.vendors.nvidia.raw, exactly as a
# bare-metal host would expose it.
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
trap 'chmod -R u+w "$WORK_DIR" 2>/dev/null; rm -rf "$WORK_DIR"' EXIT

# ── 1. Closure equality ─────────────────────────────────────────────────────
echo "==> closure equality: wheelhouse vs images (configs.yaml + app-versions.yaml)"
python3 "$REPO_ROOT/scripts/verify_bundle.py" "$TARBALL" --check-wheels

# ── 2 + 3. Install + smoke test, one network-denied container ──────────────
echo "==> install + smoke test under --network none"
mkdir -p "$WORK_DIR/bundle" "$WORK_DIR/prefix"
tar xzf "$TARBALL" -C "$WORK_DIR/bundle"

# The install runs as root in the container, so the standalone CPython lands in
# /root/.local/share/uv/python and the venv references it — which is why
# install and smoke share ONE container below.
cat > "$WORK_DIR/smoke.sh" <<'SMOKE'
set -euo pipefail
cd "/verify/bundle/${BUNDLE_NAME}"

# meta.env (written by build_bundle.py) tells us the launcher to smoke-test.
LAUNCHER="$(sed -n 's/^LAUNCHER=//p' meta.env)"
[ -n "$LAUNCHER" ] || LAUNCHER="${BUNDLE_NAME%-*}" # fallback: never expected

./install.sh --prefix /verify/prefix --app-version "${APP_VERSION}"

PREFIX="/verify/prefix"
. "$PREFIX/etc/profile.d/zz-compiler.sh"

echo "==> compiler toggle"
"$PREFIX/bin/compiler" triton
"$PREFIX/bin/compiler" flagtree

if [ -x "$PREFIX/bin/$LAUNCHER" ]; then
    echo "==> $LAUNCHER --help"
    "$PREFIX/bin/$LAUNCHER" --help >/dev/null && echo "$LAUNCHER --help OK"
fi

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
