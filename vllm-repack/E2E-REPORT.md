# vllm-repack Track B — NVIDIA cuda12.8 End-to-End Report

**Date:** 2026-07-27/28  
**Platform:** NVIDIA H20 (8×)  
**Target:** vllm 0.20.2 + vllm-plugin-FL on flagos-runtime-nvidia-cuda12.8:2.1.1

---

## 1. What We Did

### Phase 0: Design Decisions

Three key constraints from the user:

1. **No `.post1` suffix** — uv-era anti-upgrade hack, no longer needed with pip
2. **PyPI split** — vendor PyPI hosts ONLY the repacked vllm wheel (1 file). All other deps from Aliyun mirror. Don't host indirect dep repacks — maintenance burden too large
3. **Repacked vllm with deps, not `--no-deps`** — the repacked wheel retains all Requires-Dist except blacklisted ones. pip resolves safe deps naturally from Aliyun. Torch is already installed and satisfies constraints → pip skips it

### Phase 1: repack.py Modifications

#### 1a. Remove `.post1` suffix

**File:** `vllm-repack/repack.py`  
**Change:** `VERSION_SUFFIX = ""` (was `".post1"`)

With `VERSION_SUFFIX = ""`, `_bump_version()` and `_bump_dist_info_dir()` become no-ops — the repacked wheel keeps the original version. pip installs from vendor PyPI via `--extra-index-url`, and since the repacked wheel has the same version as upstream, pip finds a match on vendor PyPI first.

#### 1b. Default index to Aliyun mirror

**File:** `vllm-repack/repack.py`  
**Change:** `https://pypi.org/simple/` → `https://mirrors.aliyun.com/pypi/simple/`

Nodes cannot reach pypi.org. All downloads go through Aliyun.

#### 1c. Keep `also_repack` packages in Requires-Dist

**File:** `vllm-repack/repack.py`  
**Change:** `also_repack` packages were previously classified as `"repack"` and STRIPPED from vllm's Requires-Dist + repacked separately. Now they are classified as `"keep"` — their Requires-Dist lines are preserved, pip resolves them naturally from Aliyun.

The `also_repack` logic in `repack_indirect()` is preserved as a fallback: if an indirect dep pins an incompatible torch version, we can invoke it manually.

#### 1d. Fix METADATA blank line bug (CRITICAL)

**File:** `vllm-repack/repack.py`, function `_downgrade_metadata_version`

**Bug:** When stripping `License-File: LICENSE` and `Dynamic:` lines for Metadata-Version 2.4→2.2 downgrade, the regex replaced them with empty strings but left a blank line. In email-format METADATA, the FIRST BLANK LINE marks the end of headers. All Requires-Dist lines after that blank line were invisible to pip.

**Fix:** Changed regexes to eat the trailing newline:
```python
# Before (broken):
_LICENSE_FILE_RE = re.compile(r"^License-File:\s*.+$", re.M)
_DYNAMIC_RE = re.compile(r"^Dynamic:\s*.+$", re.M)

# After (fixed):
_LICENSE_FILE_RE = re.compile(r"^License-File:\s*.+\n?", re.M)
_DYNAMIC_RE = re.compile(r"^Dynamic:\s*.+\n?", re.M)
```

This was the root cause of "all dependencies are present in METADATA but pip doesn't see them."

#### 1e. Docstring update

Updated the module docstring to reflect the new design (2026-07-27).

### Phase 2: configs.yaml Changes

#### 2a. Bump flag_gems version

```yaml
# Before:
flaggems: "5.3.1"

# After:
flaggems: "5.3.2"
```

#### 2b. Bump numpy version (and relax in FlagGems)

```yaml
# Before:
runtime_prereqs:
  - "numpy==1.26.4"

# After:
runtime_prereqs:
  - "numpy==2.3.5"
```

Background: vllm's dependency `opencv-python-headless>=4.13.0` declares `numpy>=2; python_version >= "3.9"`. The runtime's `numpy==1.26.4` was incompatible. Investigation across all 14 backends found NO vendor torch package declares `numpy<2` — the `==1.26.4` pin was a self-imposed constraint in FlagGems' `pyproject.toml`.

### Phase 3: FlagGems Changes (separate repo)

**File:** `FlagGems/pyproject.toml`  
**Change:** `"numpy==1.26.4"` → `"numpy"` (unversioned)  
**Tag:** `v5.3.2`

### Phase 4: Build, Upload, Install, Verify

#### 4a. Download vllm wheel

```bash
# On Linux x86_64 target machine (NOT macOS!)
pip download --no-deps --dest /tmp/vllm-dl "vllm==0.20.2" \
  --index-url https://mirrors.aliyun.com/pypi/simple
```

#### 4b. Repack

```bash
python3 vllm-repack/repack.py /tmp/vllm-dl/vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl
```

Result: 7 blacklisted deps removed, 82 retained, 6 also_repack candidates kept.

#### 4c. Upload repacked wheel to vendor PyPI

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-nvidia/ \
  /tmp/vllm-repack/output/vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl
```

#### 4d. Install flow

```bash
# 1. Runtime deps (torch, flagtree, flag_gems, ...)
pip install \
  --index-url https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple \
  torch==2.10.0+cu128 torchaudio==2.10.0+cu128 torchvision==0.25.0+cu128 \
  flagtree==0.6.0 flag_gems==5.3.2 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.1 numpy==2.3.5

# 2. vllm (repacked, NO --no-deps!)
pip install \
  --index-url https://mirrors.aliyun.com/pypi/simple \
  --extra-index-url https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  vllm==0.20.2

# 3. vllm-plugin-FL (source build)
git clone https://github.com/flagos-ai/vllm-plugin-FL
cd vllm-plugin-FL
VLLM_VENDOR=cuda pip install --no-build-isolation .
```

**Key insight:** flag_gems must NOT use `--no-deps` — its `sqlalchemy==2.0.48` dependency needs to be fetched from Aliyun. Using `--find-links` for the local wheel + pip natural resolution works.

#### 4e. Start vllm serve

```bash
export VLLM_PLUGINS=fl
vllm serve /models/Qwen3.6-35B-A3B \
  --served-model-name "qwen" \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --trust-remote-code
```

#### 4f. Test inference

```json
{"model":"qwen","choices":[{"message":{"content":"Here's a thinking process:\n\n1.  **Analyze User Input:**..."}}]}
{"usage":{"prompt_tokens":17,"total_tokens":145,"completion_tokens":128}}
```

✅ Inference successful.

---

## 2. Bugs Encountered & Root Causes

| # | Symptom | Root Cause | Fix |
|---|---------|-----------|-----|
| 1 | `pip install repacked-vllm.whl` → vllm import fails with `ModuleNotFoundError: No module named 'regex'` | METADATA header ended at a blank line left by `License-File` removal. All 82 Requires-Dist lines were invisible to pip | Fix `_LICENSE_FILE_RE` / `_DYNAMIC_RE` regex to eat trailing `\n?` |
| 2 | `pip install` upgrades numpy 1.26.4 → 2.3.5, flag_gems breaks | `opencv-python-headless` declares `numpy>=2`, and flag_gems declares `numpy==1.26.4` | Relax FlagGems `pyproject.toml` from `==1.26.4` to `numpy` unversioned; bump configs.yaml pin to `2.3.5` |
| 3 | After vllm install, `sqlalchemy` completely missing | flag_gems installed with `--no-deps`, so its deps weren't fetched. vllm's resolution didn't need sqlalchemy → uninstalled | Install flag_gems without `--no-deps` (use `--find-links` for local wheel, let pip resolve deps) |
| 4 | macOS `pip download vllm==0.20.2` gives sdist with `version: 0.20.2+cpu` → inconsistent version error | macOS has no manylinux wheel; Aliyun mirror only serves sdist | Always work on target Linux x86_64 node, never on macOS |
| 5 | `vllm serve` warns `_C.abi3.so: undefined symbol: _ZN3c1013MessageLoggerC1E...` | ABI mismatch between vllm binary wheel and host CUDA — non-fatal, C extensions downgrade gracefully | Acceptable for PoC. Production needs vllm compiled against matching CUDA |

---

## 3. Architecture: What Goes Where

```
pip install vllm==0.20.2
  │
  ├── --index-url: https://mirrors.aliyun.com/pypi/simple      ← ALL safe deps
  └── --extra-index-url: https://resource.flagos.net/.../nvidia/simple  ← repacked vllm ONLY

Resolution:
  1. pip asks both indexes for vllm==0.20.2
  2. Aliyun: vllm-0.20.2.whl (original, declares torch in Requires-Dist)
  3. vendor PyPI: vllm-0.20.2.whl (repacked, torch stripped)
  4. pip picks vendor PyPI (same version, but --extra-index-url has priority in practice)
  5. pip reads repacked METADATA → no torch/triton/CUDA in Requires-Dist
  6. pip resolves remaining 82 Requires-Dist from Aliyun
  7. Some transitives (flashinfer, compressed-tensors) declare torch in their own METADATA
  8. pip sees torch already installed (2.10.0+cu128) and constraints are satisfied → SKIPS
```

---

## 4. What Can Be Automated

| Task | Automation | Status |
|------|-----------|--------|
| Download vllm wheel | `pip download` — trivial, same every time | ✅ |
| Run repack.py | Script is deterministic. Input: wheel + config.yaml | ✅ |
| Upload to vendor PyPI | `twine upload` with token — can be CI step | ✅ |
| Verify METADATA (no blank lines, correct deps) | Check: `wc -l`, `grep Requires-Dist`, count removed vs retained | ⚒️ need script |
| Build/upload to all vendor PyPIs | Loop over vendors in configs.yaml. repack is platform-agnostic (same vllm wheel for all) | ⚒️ need script |
| CI workflow: repack → upload → docker build → push | Pattern exists in `flaggems-release.yml` + `runtime.yml` | ⚒️ need workflow |
| Containerfile for app image | `FROM runtime` + pip install vllm + pip install vllm-plugin-FL | ⚒️ need Containerfile |
| Smoke test after build | `docker run --rm --gpus all <image> python3 -c 'import vllm; ...'` | ⚒️ need CI step |

## 5. What Must Remain Manual

| Task | Why |
|------|-----|
| Review config.yaml rules when vllm version bumps | New vllm version may introduce new deps that need blacklisting or new `also_repack` candidates |
| Decide whether to use `also_repack` fallback | Only if pip's resolution actually overwrites torch — needs human inspection of install log |
| Per-platform integration testing | Each vendor has different torch builds, CUDA ABIs, and device-specific quirks |
| FlagGems version bump + tag | Requires coordination with FlagGems team |
| Model download | Environment-specific, large files, needs appropriate storage |

## 6. Changes to Commit

### In build-infra (this repo)

| File | Change | PR? |
|------|--------|-----|
| `vllm-repack/repack.py` | VERSION_SUFFIX="", Aliyun default index, also_repack kept in Requires-Dist, blank-line regex fix, docstring update | Yes |
| `configs.yaml` | `flaggems: "5.3.2"`, `numpy==2.3.5` | Yes |

### In FlagGems (separate repo)

| File | Change | Status |
|------|--------|--------|
| `pyproject.toml` | `"numpy==1.26.4"` → `"numpy"` (unversioned) | Already tagged `v5.3.2` |

### New files (to create)

| File | Purpose |
|------|---------|
| `scripts/repack_vllm.py` | Download vllm wheel → repack → twine upload to all vendor PyPIs |
| `app/vllm/Containerfile` | FROM runtime → pip install vllm + vllm-plugin-FL |
| `.github/workflows/vllm-app.yml` | Full CI: repack → upload → build → verify → push |

---

## 7. Risks & Pain Points

### Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| vllm version bump introduces new blacklist-worthy deps | Medium | Review METADATA diff each bump; update config.yaml |
| Indirect dep declares incompatible torch version | Medium | Monitor pip install output; `also_repack` fallback exists |
| pip resolution behavior changes (e.g., someday always prefers newer version) | Low | Already migrated from uv; pip is stable. Re-test on pip version bumps |
| Vendor PyPI token expires or changes | Low | CI uses secrets; document token rotation |
| macOS vs Linux platform mismatch | Medium | Never repack on macOS. CI runs on H20 self-hosted runners |
| vllm binary wheel ABI incompatible with host CUDA | Low-Medium | Warning only for PoC. Production may need source build |
| flag_gems hard-pins other deps in future | Medium | Already hit with numpy + sqlalchemy. FlagGems should use `>=` not `==` for runtime deps |

### Pain Points

| Pain | Severity | Notes |
|------|----------|-------|
| SSH gateway instability | High | `no available gateway` appeared ~50% of attempts. Every tool call is a gamble |
| 244MB wheel upload takes 2-3 min per vendor | Medium | Acceptable for CI. 14 vendors = ~30 min parallelizable |
| pip dependency resolution is slow (3-5 min for vllm's 82 deps) | Low | One-time cost in Docker build; layers are cached |
| FlagGems hard-pinned deps cause cascading conflicts | Medium | `sqlalchemy==2.0.48` was installed then uninstalled. Should audit FlagGems deps for other hard pins |
| No model files on nodes | Low | One-time per-model download. Use `/data/models` for storage |
| vllm _C.abi3.so undefined symbol warning | Low | Non-fatal, but noise in logs. Needs investigation |

---

## 8. Full Stack Verification (nvidia-cuda12.8)

```
torch:        2.10.0+cu128  ✅  (from vendor PyPI)
torchaudio:   2.10.0+cu128  ✅
torchvision:  0.25.0+cu128  ✅
flagtree:     0.6.0         ✅  (default compiler)
flag_gems:    5.3.2         ✅  (from vendor PyPI, numpy relaxed)
triton:       3.6.0         ✅  (side compiler at /opt/triton)
numpy:        2.3.5         ✅  (was 1.26.4)
pybind11:     3.0.3         ✅
ninja:        1.13.0        ✅
PyYAML:       6.0.1         ✅
vllm:         0.20.2        ✅  (repacked, from vendor PyPI)
vllm_fl:      loaded        ✅  (source build, VLLM_VENDOR=cuda)
CUDA:         True          ✅  (nvidia-smi works)
Inference:    Qwen3.6-35B-A3B ✅  (prompt_tokens=17, completion_tokens=128)
```

---

## 9. Next Steps

1. **Commit & PR** `repack.py` + `configs.yaml` changes to build-infra
2. **Build & publish** flag_gems 5.3.2 wheels to all vendor PyPIs
3. **Write** `scripts/repack_vllm.py` for CI automation
4. **Write** `app/vllm/Containerfile`
5. **Expand to nvidia-cuda13.3** (same pattern, different torch version)
6. **Multi-vendor rollout** — metax, hygon, iluvatar, mthreads, kunlunxin, cambricon (CUDA-path)
