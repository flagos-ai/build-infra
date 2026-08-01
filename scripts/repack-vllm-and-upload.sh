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

# ============================================================
# repack-vllm-and-upload.sh — Build, repack, and upload vllm for any backend
# ============================================================
#
# Usage:
#   ./repack-vllm-and-upload.sh --vendor <vendor> --backend <backend> [--vllm-version X.Y.Z]
#
# Examples:
#   ./repack-vllm-and-upload.sh --vendor mthreads --backend musa5.2.0
#   ./repack-vllm-and-upload.sh --vendor metax --backend maca3.7.2.1 --vllm-version 0.20.2
#
# Prerequisites:
#   - Docker with harbor.baai.ac.cn access
#   - python3 + pyyaml on the host
#   - flagos-runtime-<vendor>-<backend>:<version>-build image exists
#   - Twine credentials for upload (or use --skip-upload)
#
# Features:
#   - Downloads vllm source from flagos-filestore
#   - Builds with VLLM_TARGET_DEVICE=empty (universal)
#   - Repacks with +flagos version suffix
#   - Uploads to vendor-specific PyPI

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

VENDOR=""
BACKEND=""
VLLM_VERSION="0.20.2"
SKIP_UPLOAD=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --vendor) VENDOR="$2"; shift 2 ;;
        --backend) BACKEND="$2"; shift 2 ;;
        --vllm-version) VLLM_VERSION="$2"; shift 2 ;;
        --skip-upload) SKIP_UPLOAD=true; shift ;;
        --help)
            echo "Usage: $0 --vendor <vendor> --backend <backend> [options]"
            echo ""
            echo "Options:"
            echo "  --vendor <name>       Vendor name (e.g., mthreads, metax, nvidia)"
            echo "  --backend <name>      Backend name (e.g., musa5.2.0, maca3.7.2.1, cuda12.8)"
            echo "  --vllm-version <ver>  vLLM version to build (default: 0.20.2)"
            echo "  --skip-upload         Skip PyPI upload, only build and repack"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$VENDOR" || -z "$BACKEND" ]]; then
    echo "Error: --vendor and --backend are required"
    exit 1
fi

# ── Configuration ───────────────────────────────────────────────────────

VENDOR_BACKEND="${VENDOR}-${BACKEND}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/vllm-repack-${VENDOR}-${BACKEND}"
FILESTORE="https://resource.flagos.net/repository/flagos-filestore"
VENDOR_PYPI="https://resource.flagos.net/repository/flagos-pypi-${VENDOR}"

# Read stack version from configs.yaml
if [[ -f "${SCRIPT_DIR}/../configs.yaml" ]]; then
    STACK_VERSION=$(python3 -c "
import yaml
with open('${SCRIPT_DIR}/../configs.yaml') as f:
    print(yaml.safe_load(f)['version'])
")
else
    echo "Error: configs.yaml not found"
    exit 1
fi

BUILD_IMAGE="harbor.baai.ac.cn/flagos-runtime/flagos-runtime-${VENDOR_BACKEND}:${STACK_VERSION}-build"
CONTAINER="vllm-repack-${VENDOR}-${BACKEND}"

echo "========================================"
echo "vLLM Repack and Upload"
echo "========================================"
echo "Vendor:        ${VENDOR}"
echo "Backend:       ${BACKEND}"
echo "vLLM Version:  ${VLLM_VERSION}"
echo "Stack Version: ${STACK_VERSION}"
echo "Build Image:   ${BUILD_IMAGE}"
echo "Work Dir:      ${WORK_DIR}"
echo "Upload Target: ${VENDOR_PYPI}"
echo ""

# ── Cleanup function ────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "==> Cleaning up container..."
    docker rm -f "${CONTAINER}" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: Prepare directories and repack scripts ──────────────────────

echo "==> Step 1: Preparing work directory"

rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"/{src,empty,output,cache}

# Copy repack scripts
cp "${SCRIPT_DIR}/../vllm-repack/repack.py" "${WORK_DIR}/"
cp "${SCRIPT_DIR}/../vllm-repack/config.yaml" "${WORK_DIR}/"

# ── Step 2: Start build container ───────────────────────────────────────

echo ""
echo "==> Step 2: Starting build container"

docker rm -f "${CONTAINER}" 2>/dev/null || true
docker pull "${BUILD_IMAGE}" > /dev/null 2>&1 || true

docker run -d --name "${CONTAINER}" \
    -v "${WORK_DIR}:${WORK_DIR}" \
    --network host \
    "${BUILD_IMAGE}" \
    sleep infinity

echo "    Container started: ${CONTAINER}"

# ── Step 3: Download vllm source from filestore ─────────────────────────

echo ""
echo "==> Step 3: Downloading vllm source from filestore"

SRC_TAR="vllm-${VLLM_VERSION}.tar.gz"
SRC_URL="${FILESTORE}/vllm/vllm-${VLLM_VERSION}.tar.gz"

docker exec "${CONTAINER}" bash -c "
    set -e
    cd ${WORK_DIR}
    echo "    Downloading ${SRC_URL}..."
    curl -sL -o ${SRC_TAR} '${SRC_URL}'
    tar xzf ${SRC_TAR} -C src/
    mv src/vllm-${VLLM_VERSION} src/vllm
    rm ${SRC_TAR}
    echo "    Source extracted to: ${WORK_DIR}/src/vllm"
"

# ── Step 4: Build empty wheel ───────────────────────────────────────────

echo ""
echo "==> Step 4: Building empty wheel (VLLM_TARGET_DEVICE=empty)"

docker exec "${CONTAINER}" bash -c "
    set -e
    cd ${WORK_DIR}/src/vllm

    # Install build dependencies
    pip install -q 'setuptools-scm>=8,<10' wheel 2>/dev/null || true

    # Build empty wheel
    export VLLM_TARGET_DEVICE=empty
    export MAX_JOBS=\$(nproc)

    echo "    Building wheel..."
    pip wheel --no-build-isolation --no-deps -w ${WORK_DIR}/empty . 2>&1 | tail -5

    echo "    Built wheel:"
    ls -lh ${WORK_DIR}/empty/*.whl
"

# ── Step 5: Create repack script with +flagos suffix ────────────────────

echo ""
echo "==> Step 5: Creating repack script with +flagos suffix"

cat > "${WORK_DIR}/repack_flagos.py" << 'REPACK_EOF'
#!/usr/bin/env python3
import re
import sys
from pathlib import Path

# Import original repack functions
sys.path.insert(0, str(Path(__file__).parent))
from repack import (
    load_config, ensure_dirs, read_wheel_metadata, parse_requires_dist,
    classify, rewrite_wheel, sha256_file, wheel_name_to_filename,
    _strip_requires_dist_lines, _downgrade_metadata_version, _strip_local_version,
    _read_wheel_file, _get_wheel_tag, _rewrite_wheel_tag, OUTPUT_DIR, CACHE_DIR,
    repack_recursive, _NAME_RE, _normalize, _VLLM_PLATFORM_TAG
)
import yaml
from datetime import datetime, timezone

def add_flagos_suffix(metadata_text: str) -> str:
    """Add +flagos suffix to Version line in METADATA."""
    def replace_version(match):
        version = match.group(1).strip()
        if '+flagos' not in version:
            return f"Version: {version}+flagos"
        return match.group(0)
    return re.sub(r'^(Version:\s*)(.+)$', replace_version, metadata_text,
                  flags=re.MULTILINE | re.IGNORECASE)

def repack_with_flagos(whl_path):
    """Repack wheel with +flagos version suffix."""
    config = load_config()
    ensure_dirs()

    print(f"Repacking: {whl_path.name}")

    # Read METADATA
    meta_text, dist_info_dir = read_wheel_metadata(whl_path)
    old_dist_info_dir = dist_info_dir

    # Handle local version suffix (strip +empty first)
    stripped = re.sub(r'\+[^.]*', '', dist_info_dir)
    has_local = stripped != dist_info_dir
    if has_local:
        dist_info_dir = stripped
        meta_text = _strip_local_version(meta_text)
        print(f"  strip local version: {old_dist_info_dir} -> {dist_info_dir}")

    # Add +flagos suffix to version
    meta_text = add_flagos_suffix(meta_text)
    print("  added +flagos version suffix")

    # Read and fix WHEEL file tag
    wheel_text = _read_wheel_file(whl_path, old_dist_info_dir)
    wheel_tag = _get_wheel_tag(wheel_text)
    if wheel_tag == "py3-none-any":
        wheel_tag = _VLLM_PLATFORM_TAG
        wheel_text = _rewrite_wheel_tag(wheel_text, wheel_tag)
        print(f"  platform tag: py3-none-any -> {wheel_tag}")
    else:
        wheel_text = None

    # Parse and classify requires-dist
    all_rd = parse_requires_dist(meta_text)
    removed = {"torch_chain": [], "cuda_only": [], "orphaned": []}
    retained = []

    for rd in all_rd:
        cat = classify(rd, config)
        if cat in ("torch_chain", "cuda_only", "orphaned"):
            removed[cat].append(rd["raw"])
        else:
            retained.append(rd["raw"])

    print(f"  keep: {len(retained)}")
    for cat in ("torch_chain", "cuda_only", "orphaned"):
        if removed[cat]:
            print(f"  {cat}: {len(removed[cat])}")

    # Get package name and version for manifest
    pkg_name = None
    pkg_version = None
    mvn = re.search(r'^Name:\s*(.+)$', meta_text, re.MULTILINE | re.IGNORECASE)
    mvv = re.search(r'^Version:\s*(.+)$', meta_text, re.MULTILINE | re.IGNORECASE)
    if mvn:
        pkg_name = mvn.group(1).strip()
    if mvv:
        pkg_version = mvv.group(1).strip()

    # Strip blacklisted deps
    names_to_remove = set()
    for cat in ("torch_chain", "cuda_only", "orphaned"):
        for rd_raw in removed.get(cat, []):
            nm = _NAME_RE.match(rd_raw)
            if nm:
                names_to_remove.add(_normalize(nm.group(1)))

    new_meta = _strip_requires_dist_lines(meta_text, names_to_remove)
    new_meta = _downgrade_metadata_version(new_meta)

    # Build output filename - need to inject +flagos into wheel name
    output_name = wheel_name_to_filename(
        pkg_name or "package",
        (pkg_version or "0.0.0").replace("+flagos", ""),
        wheel_tag
    )
    # Inject +flagos before the platform tag
    output_name = output_name.replace("-cp38", "+flagos-cp38")
    output_name = output_name.replace("-py3", "+flagos-py3")

    output_path = OUTPUT_DIR / output_name
    rewrite_wheel(whl_path, output_path, new_meta, dist_info_dir,
                  old_dist_info_dir, wheel_text)

    # Recursive indirect dep audit
    repacked_deps = []
    print(f"\n=== Recursive dependency audit ===")
    results = repack_recursive(new_meta, [])
    for dep_name, dep_version, dep_whl, dep_manifest in results:
        repacked_deps.append({
            "package": dep_name,
            "version": dep_version,
            "wheel": dep_whl.name,
            "manifest": dep_manifest.name,
        })

    # Write manifest
    manifest_path = OUTPUT_DIR / f"{_normalize(pkg_name or 'unknown')}-{pkg_version or 'unknown'}.deps-manifest.yaml"
    manifest_data = {
        "source_wheel": whl_path.name,
        "source_sha256": sha256_file(whl_path),
        "package": pkg_name,
        "version": pkg_version,
        "modified_at": datetime.now(timezone.utc).isoformat(),
        "removed": {k: v for k, v in removed.items() if v},
        "repacked_deps": repacked_deps,
        "retained": retained,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nDone:")
    print(f"  wheel:    {output_path}")
    print(f"  manifest: {manifest_path}")
    if repacked_deps:
        print(f"  indirect: {len(repacked_deps)} repacked")

    return output_path, manifest_path

if __name__ == "__main__":
    from pathlib import Path
    whl_path = Path(sys.argv[1])
    repack_with_flagos(whl_path)
REPACK_EOF

docker cp "${WORK_DIR}/repack_flagos.py" "${CONTAINER}:${WORK_DIR}/"

# ── Step 6: Repack wheel ────────────────────────────────────────────────

echo ""
echo "==> Step 6: Repacking wheel"

docker exec "${CONTAINER}" bash -c "
    cd ${WORK_DIR}
    python3 ${WORK_DIR}/repack_flagos.py ${WORK_DIR}/empty/vllm-*.whl
"

# ── Step 7: Report results ──────────────────────────────────────────────

echo ""
echo "==> Step 7: Repack complete"
echo ""
echo "Output files:"
docker exec "${CONTAINER}" bash -c "ls -lh ${WORK_DIR}/output/"

# ── Step 8: Upload to vendor PyPI ───────────────────────────────────────

if [[ "$SKIP_UPLOAD" == true ]]; then
    echo ""
    echo "==> Step 8: Skipping upload (--skip-upload specified)"
else
    echo ""
    echo "==> Step 8: Uploading to vendor PyPI"
    echo ""
    echo "    Target: ${VENDOR_PYPI}"
    echo ""

    # Check for twine
    if ! command -v twine > /dev/null 2>&1; then
        echo "    Installing twine..."
        pip install -q twine
    fi

    # Upload
    echo "    Uploading wheels..."
    twine upload \
        --repository-url "${VENDOR_PYPI}" \
        "${WORK_DIR}/output/"*.whl \
        2>&1 | grep -v "^Uploading" | head -20 || true

    echo ""
    echo "    Upload complete!"
fi

# ── Summary ─────────────────────────────────────────────────────────────

echo ""
echo "========================================"
echo "Summary"
echo "========================================"
echo "Vendor:           ${VENDOR}"
echo "Backend:          ${BACKEND}"
echo "vLLM Version:     ${VLLM_VERSION}+flagos"
echo ""
echo "Work directory:   ${WORK_DIR}"
echo "Output wheels:    ${WORK_DIR}/output/"
echo ""
echo "To verify installation:"
echo "  pip install --index-url ${VENDOR_PYPI}/simple vllm==${VLLM_VERSION}"
echo ""
