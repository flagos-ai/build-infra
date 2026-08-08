# Enflame (GCU300) vLLM Inference — Investigation Log (dsinvest)

**Date:** 2026-08-06 → 2026-08-08
**Backend:** `flagos-runtime-enflame-tops1.9.10:2.1.2` (rebuilt; dual-compiler side-dir layout per PR #332)
**Goal:** vllm repack E2E on Enflame — serve starts, inference gives **clean** output.
**Result:** serve starts; **inference output is deterministic garbage** ("泥修士apas矛一时…"). Root cause NOT yet found despite extensive isolation. This log records everything tried.

---

## 1. What works (verified)

| item | status |
|---|---|
| Compiler side-dir layout (`/opt/flagtree` + `/opt/triton`, site-packages clean) | ✅ (rebuilt image; PR #332) |
| `compiler triton` switch → `/opt/triton`, `triton_gcu` registers `gcu` | ✅ |
| `compiler` status label (flagtree vs triton) | ✅ after fix (PR #338) |
| flash_attn ABI (torch-2.10.0 build) | ✅ (PR #310) |
| int32 flash kernel (`virtual_to_cache_offset` + philox int32) | ✅ compiles + runs |
| flag_gems flash **non-paged** (sq=8, sk=16/32/64) vs torch ref | ✅ 0.007–0.008 |
| flag_gems flash **paged** (sq=1/8, sk=16/32/64) vs **kernel-convention** ref | ✅ 0.002–0.004 |
| embedding gather | ✅ 0.0 |
| fp32-upcast mm (via direct `F.linear(x.float(), w.float())`) | ✅ 0.0001 |
| vllm serve startup (TP=1, enforce-eager, gpu-util 0.5) | ✅ `Application startup complete` |

## 2. The core problem

`vllm serve /models/Qwen3-4B` starts, but inference returns **deterministic garbage**:
- prompt "The capital of France is" → `"泥修士apas矛一时OfYear民間<>较好oins1 expected候…"`
- even "Paris is the capital of" → `"本这是一门 ✔哪esris"` — broken from the **first generated token**.

The garbage is identical/stable across many config changes, which strongly implicates one fixed wrong computation (not accumulation, not flakiness).

## 3. Configs tested (all → garbage)

| change | result |
|---|---|
| `VLLM_FL_PREFER=flagos / vendor / reference` | identical garbage |
| `ENABLE_I64_CHECK=0` (vendor env) | no change |
| `TORCHGCU_INDUCTOR_ENABLE=1` (vendor env) | **crashes at import** (torch_gcu inductor patch imports missing `disable_pointwise_autotuning`) |
| fp32-upcast mm (patch `vllm default_unquantized_gemm`) | still garbage |
| + fp32-upcast rms_norm/silu (vendor.gcu impls) | **output changed** but still garbage |
| + fp32-upcast rotary (vendor.gcu) | no further change |
| force rms/rotary/silu → vendor.gcu via gcu.yaml | still garbage |
| TP=8 vs TP=1 | both garbage |
| `--dtype float16` | empty output (different failure) |

The only config that CHANGED the output was the rms_norm+silu fp32 patch (garbage became a different garbage) — so rms/silu contribute, but the dominant error is elsewhere.

## 4. Root-cause hunt — what was isolated

### 4a. The flash-kernel "paged bug" was a red herring
- Earlier found "paged flash wrong (2.7)" — turned out to be a **wrong causal-mask reference** in my probe.
- The kernel's causal convention: `col_rb = min(sk-1, row_idx + sk - sq)` (query rows are the LAST `sq` of the `sk`-length sequence — correct for vllm).
- With the correct ref, **paged flash is correct (0.002–0.004)**. The flash kernel is NOT the bug.

### 4b. GCU300 bf16 arithmetic is imprecise at scale — but fp32-upcast fixes each op
Measured (bf16 on GCU, 4096×4096, vs fp32 torch):
| op | bf16 max_diff | fp32 max_diff |
|---|---|---|
| matmul (`F.linear`/`@`) | **0.50** | 0.0001 |
| rms_norm | **0.10** | 0.0000 |
| rotary | **0.06** | 0.0000 |
| silu | **0.016** | — |
| embedding gather | 0.0 | — |

**Fix per op = fp32 upcast.** The linear GEMM fp32 patch (via `vllm default_unquantized_gemm`, confirmed fired 290×) and vendor.gcu rms/silu/rotary fp32 patches were applied and confirmed active.

### 4c. flag_gems.enable() does NOT override torch.mm on GCU
- `a @ b` with `flag_gems.enable()` still uses torch native mm (0.5), NOT flag_gems.mm (verified: flag_gems.mm never called).
- So the model's dense GEMMs run through **torch native bf16 mm** → the vllm `default_unquantized_gemm` patch (fp32-upcast) is the correct interception point, and it fired.

### 4d. The remaining unknown
With **all** of these fp32-patched and active:
- linear GEMMs (fp32, exact) ✅
- rms_norm, silu, rotary (vendor.gcu fp32, exact) ✅
- flash (paged + non-paged, correct) ✅
- embedding (exact) ✅
- **→ still garbage from the first token.**

The dispatch log confirms: `attention_backend → vendor.gcu` → (via `_vllm_fa2_C` fallback) **AttentionFLBackend (flag_gems flash)**; rms/rotary/silu on vendor.gcu; `FP32_GEMM_DEBUG` fired 290×.

**Unresolved suspects (not yet isolated):**
1. The **attention at the REAL vllm decode shape** — my synthetic paged tests used my own shapes; vllm's actual q/k/v/page-table layout may differ. Instrumenting `AttentionFLBackend.forward` was started (dump q shape+sum) but the patch introduced a **SyntaxError** (`import os as _os` line — indentation/insertion bug in my instrument) that crashed serve; container cleaned up before re-test.
2. An **unpatched bf16 op in the vllm forward** that I haven't identified (e.g. a fused kernel, the MoE, the KV-cache `gather_bf16_kv_from_pages` — though it's `NotImplementedError` in flaggems and likely not called in decode).
3. **vllm_flash_attn / vendor flash_attn** being used despite the fallback (the `_vllm_fa2_C` import check might pass in some path).

## 5. Vendor env vars (from Enflame)
The vendor recommended:
- `TORCH_GCU_ENABLE_INT64_AND_UINT64=1` — already baked (image env).
- `ENABLE_I64_CHECK=0` — image bakes `1`; setting `0` didn't change output.
- `TORCHGCU_INDUCTOR_ENABLE=1` — **not usable on this torch_gcu/torch** (import crash).

## 6. Image/compiler issues found (separate from the inference garbage)
- **PR #338** (merged): `compiler` status label said "triton" on both — fixed (dirname twice).
- The dual-compiler side-dir layout itself works; flagtree/triton switch is hermetic.

## 7. Next steps (if resumed)
1. **Fix the attention instrumentation** (the SyntaxError was my insertion bug — the `import os as _os` block landed at wrong indentation) and dump the actual `q` + flash output at the first decode step.
2. Compare that q to a CPU/float reference of the same weights (run Qwen3-4B forward on CPU for the same prompt, dump layer-0 q) — if q differs, the error is in the QKV projection (despite fp32 mm); if q matches but flash output differs, it's the attention path.
3. Check whether the `reshape_and_cache_flash` / KV write path corrupts the cached KV (bf16 write) — decode reads back garbage KV.
4. Consider `vllm_flash_attn` (vendor) attention as a control — is it any different from flag_gems flash at real shape?

## Artifacts
- Container `vllm-verify-enflame-new` (rebuilt image) — **removed** after the session; state was: plugin fixes + int32 flash + fp32 patches + attention instrumentation (broken syntax). Re-create from the rebuilt image and re-apply `scripts`-less manual patches (they were container-local).
- `gcu-fix2/` on enflame1 `/tmp` (the 5 plugin fix files) — still there.
- FlagGems flash is correct; the int32 kernel patch is the only flag_gems change needed for numerics.
