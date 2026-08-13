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

# ============================================================
# verify-megatron-backend.sh — Install and verify megatron-core on a backend
# ============================================================
#
# STUB — to be filled during the hygon25 verification phase.
#
# Facility 2 verification: install the repacked megatron-core wheel into a
# `flagos-runtime-{vendor}-{backend}` container and prove the dependency
# surgery held — i.e. the carefully crafted torch/triton/flag_gems matrix is
# byte-for-byte unchanged after the install, and megatron.core actually loads.
#
# Usage (intended):
#   verify-megatron-backend.sh <vendor-backend>
#   verify-megatron-backend.sh hygon-dtk26.04
#
# Prerequisites (intended):
#   - Running on the target node with hardware access
#   - Repacked megatron-core wheel (with +flagos suffix) uploaded to the
#     vendor PyPI (flagos-pypi-<vendor>)

set -euo pipefail

# ── Parse arguments ─────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <vendor>-<backend>" >&2
    exit 1
fi

VENDOR_BACKEND="$1"
VENDOR="${VENDOR_BACKEND%-*}"
BACKEND="${VENDOR_BACKEND#*-}"

# ── TODO: fill during verification ─────────────────────────────────────
# 1. Resolve STACK_VERSION from ${SCRIPT_DIR}/../configs.yaml; start a
#    runtime container with the vendor's run flags (build-config.yml `run:`),
#    mirroring packaging/vllm/verify-vllm-backend.sh.
# 2. BEFORE snapshot: record versions of torch / triton / flag_gems / numpy
#    (+ their site-package paths) inside the container.
# 3. Single-step install (no --no-deps):
#      pip install --index-url "https://resource.flagos.net/repository/flagos-pypi-${VENDOR}/simple" \
#                  --extra-index-url "https://mirrors.aliyun.com/pypi/simple" \
#                  "megatron-core==<version>+flagos"
# 4. AFTER snapshot: compare each package version to BEFORE — must be equal
#    item by item, or the install corrupted the matrix (fail).
# 5. Import check: source the vendor env if needed (hygon:
#    `source /opt/dtk-26.04/env.sh`), then
#      python3 -c "import megatron.core; print(megatron.core.__version__)"
#    and confirm `helpers_cpp` is importable (megatron.core.datasets.helpers_cpp).
# 6. Report before/after table + import result.

echo "STUB: verify pipeline for ${VENDOR_BACKEND} not implemented yet." >&2
echo "      See report-megatron-0.17.1.md §2.2 for the design." >&2
exit 1
