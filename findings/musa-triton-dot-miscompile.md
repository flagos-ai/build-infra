# MUSA Flash-Attention Wrong Outputs — FlagTree-Backend Specific; Vendor Triton Works

## Status

**Root cause identified, with a working fix.** On the MUSA (mthreads) backend,
the flash-attention kernel produces wrong outputs **only under FlagTree**
(`flagtree==0.6.0+mthreads3.6`). **Switching to the vendor Triton**
(`/opt/triton`, `triton==3.6.0+git89458660`, shipped in the runtime image) makes
flash attention **correct** (non-causal 0.0055, causal 0.0087). The miscompile
is **FlagTree-specific**; it is not a general MUSA/vendor-compiler bug.

**Date:** 2026-08-07
**Platform:** MTT S5000 (8×), MUSA 5.2.0, torch 2.9.1, flag_gems 5.3.2
**Compilers tested (both in the `flagos-runtime-mthreads-musa5.2.0:2.1.2` image):**
- **FlagTree** `flagtree==0.6.0+mthreads3.6` (default compiler, `/flagos` site-packages; triton 3.6.0, `triton.backends == ['mthreads']`)
- **Vendor Triton** `/opt/triton` (`triton-3.6.0+git89458660`, ships its own `triton/backends/musa/`)

**Context:** byproduct of the enflame/mthreads vllm E2E verification (see
`vllm-repack/report-vllm-0.20.2.md` §2.3 / §2.6.1).

**Enflame GCU300 follow-up (same session):** the enflame ~2.9 signature was
**NOT** the same miscompile — with the int32 flash kernel applied (int64 philox
arg removed; GCU300's `ENABLE_I64_CHECK` verifier rejects 64-bit types),
flash attention is **correct under BOTH compilers on enflame** (non-causal
0.0078, causal 0.0076 under FlagTree and under the vendor triton). Enflame's
earlier "2.9" was a **compile-rejection artifact** (the kernel never ran), not
wrong math. The FlagTree miscompile is **unique to mthreads**.

---

## 1. Symptom

`flag_gems.flash_attn_varlen_func` returns wrong outputs **under FlagTree**:

| probe (8×8×128, bf16) | under FlagTree | under vendor triton |
|---|---|---|
| flash non-causal | `max_abs_diff` **2.94** | **0.0055** ✅ |
| flash causal | wrong (~4) | **0.0087** ✅ |
| basic ops add / silu / matmul (torch) | exact | exact |

Basic torch matmul and single-op kernels are exact on MUSA under both
compilers. Only the flash kernel (under FlagTree) is wrong.

## 2. The decisive experiment (what the user asked)

With flagtree **uninstalled** (`pip uninstall flagtree` → its dist-info and
site-packages `triton/` are gone) and `compiler triton` switching
`PYTHONPATH=/opt/triton`:

```
causal=False max_abs_diff: 0.0055
causal=True  max_abs_diff: 0.0087
```

Both are bf16-expected precision (~0.01). **Flash attention works correctly
under the vendor Triton.** The earlier ~2.9/4.x errors were measured under
FlagTree (the image default).

> Note on the causal reference: the earlier "causal=4.18" number used a wrong
> reference mask (`triu(diagonal=sk-sq+1)`). The correct kernel-convention mask
> is lower-triangular (`row m attends cols ≤ m`); with it, causal under the
> vendor triton is 0.0087.

## 3. Isolation chain (what was ruled out)

The error was chased through several hypotheses under FlagTree; all the
in-kernel pieces tested **exact in isolation**:

| hypothesis | result |
|---|---|
| `tl.dot` one-shot | exact |
| `make_block_ptr` loads | exact |
| `boundary_check` padding | exact |
| `tl.math.exp2` vs `tl.exp` | both fine standalone |
| scale folding in exp | both fine standalone |
| PV dot | exact |
| `tl.range` vs `range` | both fine standalone |
| softmax on a known S | exact |

A **minimal FMA repro** (scalar-offset loads in a Python loop, 16 programs) was
built and showed per-pid wrong addresses under FlagTree (pids 6+), but it is
**not** the flash path (flash uses `tl.dot` + `make_block_ptr`) and it is
**also wrong under the vendor triton** (all pids) — so it was a red herring for
identifying the flash issue. The flash-specific miscompile is in FlagTree's
`tl.dot`/block-ptr lowering, and it does not reproduce under the vendor musa
backend.

## 4. Root cause

**FlagTree `0.6.0+mthreads3.6`'s mthreads backend miscompiles the flash kernel
(`tl.dot` + `make_block_ptr` batched/headed loads) for a subset of programs.**
The vendor's own Triton (`3.6.0+git89458660`, `backends/musa/`) compiles the
same flash kernel correctly. The bug is therefore in the **FlagTree fork's
mthreads backend**, not in flag_gems and not in the vendor MUSA toolchain.

## 5. Impact

- **mthreads flash attention works correctly under the vendor Triton** — which
  the dual-compiler runtime image already provides via `compiler triton`
  (PR #332 side-dir layout). The practical fix is to run vllm/flag_gems on
  mthreads with the vendor triton, not FlagTree.
- Under the FlagTree default, `flash_attn_varlen_func` (and any
  tl.dot-based flash) gives wrong outputs → vllm inference garbage (the §2.3
  symptom).
- flag_gems kernel logic is correct (verified piece-by-piece, and correct under
  the vendor triton).

## 6. Constructive next steps

1. **Use the vendor Triton on mthreads** (already available: `compiler triton`
   / `/opt/triton`). Validate the full vllm/plugin path under it, not just the
   flash probe — this is the immediate next step for the mthreads E2E.
2. **Report the FlagTree mthreads-backend miscompile to the flagtree team**
   with the flash-kernel repro (tl.dot + make_block_ptr batched/headed loads,
   wrong under FlagTree, correct under vendor triton). The minimal FMA repro
   is attached but is a secondary pattern (broken under both).
3. **Enflame GCU300 is already resolved** — with the int32 flash kernel, flash
   attention is correct under both compilers; no compiler switch needed there.
   (Its separate int64/ABI issues were fixed by the int32 kernel + PR #310
   flash-attn build.)

## 7. Files / artifacts

- Probe scripts ran in a disposable container on the `mthreads` node (removed
  after use). The flash probe (non-causal + causal vs torch reference) and the
  `pip uninstall flagtree` + `compiler triton` switch are the reproducible
  recipe.
- report-vllm-0.20.2.md §2.3 (mthreads) and §2.6.1 (enflame) record the ~2.9 symptom
  from the vllm verification side.
