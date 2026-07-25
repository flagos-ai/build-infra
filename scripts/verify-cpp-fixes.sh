#!/usr/bin/env bash
# === verify-cpp-fixes.sh ============================================
# Run inside the runtime:v1 container to verify FlagGems + libtriton_jit
# fixes before the PRs are merged.
#
# Env vars (all required):
#   FLAGGEMS_REPO            — FlagGems git URL (fork with fix)
#   FLAGGEMS_REF             — branch/tag to check out
#   LIBTRITON_JIT_REPO       — libtriton_jit git URL
#   LIBTRITON_JIT_REF        — branch/tag to check out
# =====================================================================
set -euo pipefail

# ── Clone fix branches ─────────────────────────────────────────────
echo "=== Cloning FlagGems ($FLAGGEMS_REF) ==="
git clone --quiet --depth 1 --branch "$FLAGGEMS_REF" "$FLAGGEMS_REPO" /tmp/FlagGems
cd /tmp/FlagGems
echo "FlagGems @ $(git describe --tags 2>/dev/null || git rev-parse --short HEAD)"

echo "=== Cloning libtriton_jit ($LIBTRITON_JIT_REF) ==="
git clone --quiet --depth 1 --branch "$LIBTRITON_JIT_REF" "$LIBTRITON_JIT_REPO" /tmp/libtriton_jit
echo "libtriton_jit @ $(git -C /tmp/libtriton_jit describe --tags 2>/dev/null || git -C /tmp/libtriton_jit rev-parse --short HEAD)"

# ── Point cpp/CMakeLists.txt at the local libtriton_jit clone ──────
echo "=== Patching CMakeLists.txt to use local libtriton_jit ==="
sed -i "s|URL https://resource.flagos.net/repository/flagos-filestore/libtriton_jit/libtriton_jit-0.2.0-rc0.1.tar.gz|SOURCE_DIR /tmp/libtriton_jit|" cpp/CMakeLists.txt
grep SOURCE_DIR cpp/CMakeLists.txt

# ── Set vendor ─────────────────────────────────────────────────────
echo "=== Setting cpp vendor: cuda ==="
tools/set_cpp_vendor.sh cuda

# ── Install FlagGems build deps ────────────────────────────────────
echo "=== Installing build deps ==="
pip install scikit-build-core pybind11 cmake ninja

# ── Build + install pure Python wheel ──────────────────────────────
echo "=== Building pure Python wheel ==="
pip wheel . --no-deps -w /tmp/wheels
PURE_WHEEL=$(ls /tmp/wheels/flag_gems-*.whl | head -1)
echo "Pure wheel: $PURE_WHEEL"
pip install --no-deps "$PURE_WHEEL"

# ── Build + install cpp wheel ──────────────────────────────────────
echo "=== Building cpp wheel ==="
CMAKE_ARGS="-DFLAGGEMS_BUILD_C_EXTENSIONS=ON -DFLAGGEMS_BACKEND=CUDA -DCMAKE_BUILD_TYPE=Release" \
  pip wheel ./cpp --no-deps -w /tmp/wheels-cpp
CPP_WHEEL=$(ls /tmp/wheels-cpp/flag_gems_cpp_*.whl | head -1)
echo "Cpp wheel: $CPP_WHEEL"
pip install --no-deps "$CPP_WHEEL"

# ── Check .so presence ─────────────────────────────────────────────
echo "=== Checking cpp .so ==="
SO=$(find "$VIRTUAL_ENV" -name "c_operators*.so" 2>/dev/null | head -1)
if [ -z "$SO" ]; then
  echo "ERROR: c_operators .so not found" >&2
  find "$VIRTUAL_ENV" -name "*.so" 2>/dev/null
  exit 1
fi
echo ".so: $SO"

# ── Check triton_src is shipped ────────────────────────────────────
echo "=== Checking triton_src ==="
find "$VIRTUAL_ENV" -path "*/flag_gems/*" -name "fill.py" 2>/dev/null | head -5
find "$VIRTUAL_ENV" -path "*/flag_gems/*" -name "copy.py" 2>/dev/null | head -5

# ── Check gen_ssig.py is shipped ───────────────────────────────────
echo "=== Checking gen_ssig.py ==="
find "$VIRTUAL_ENV" -name "gen_ssig.py" 2>/dev/null | head -3

# ── Run the Python verification ────────────────────────────────────
echo "=== Running verification test ==="
python3 /tmp/verify-cpp-ops.py

echo "=== Verification complete ==="
