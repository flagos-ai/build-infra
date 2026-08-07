# MUSA Triton `tl.dot`/FMA Load-Address Miscompile — Root-Cause Report

## Status

**Root cause found and reproduced** on the MUSA (mthreads) backend. This is a
vendor compiler bug, not a flag_gems kernel-logic bug. It surfaces as
data-dependent wrong outputs in batched/headed flash-attention kernels.

**Date:** 2026-08-07
**Platform:** MTT S5000 (8×), MUSA 5.2.0, torch 2.9.1, flag_gems 5.3.2 (flagtree
compiler, generic flash kernel)
**Context:** byproduct of the enflame/mthreads vllm E2E verification (see
`vllm-repack/E2E-REPORT.md` §2.3 / §2.6.1). The enflame GCU300 backend shows
the same ~2.9 error signature; this report isolates the mechanism on mthreads,
where it is cleanly reproducible.

---

## 1. Symptom

`flag_gems.flash_attn_varlen_func` on MUSA returns **wrong outputs** (garbage in
vllm inference):

| probe | result |
|---|---|
| flash `flash_attn_varlen_func` non-causal (8×8, bf16) | `max_abs_diff` **2.94** |
| flash `flash_attn_varlen_func` causal | `max_abs_diff` **4.18** |
| basic ops add / silu / matmul (torch) | exact (0 / 4.8e-7 / 0) |

The same kernel is **exact on NVIDIA**. Basic torch matmul is exact on MUSA —
only Triton kernels with batched/headed loads are wrong.

## 2. Isolation chain (what was ruled out)

The error was chased through several hypotheses, all eliminated:

| hypothesis | test | result |
|---|---|---|
| `tl.dot` itself | one-shot `tl.dot` (fp32/bf16 in) | **exact** (0.0 / 3.8e-6) |
| `make_block_ptr` loads | block-ptr + `tl.dot` QK | **exact** (3.8e-6) |
| `boundary_check` padding | block-ptr with boundary_check | **exact** (4.8e-7) |
| `tl.math.exp2` vs `tl.exp` | softmax with either | both wrong in-kernel; both fine standalone |
| scale folding (`(S−max)·scale`) | exp with scale inside/outside | both wrong in-kernel; both fine standalone |
| PV dot (`P.to(bf16)` / fp32) | PV dot isolated | **exact** (0.0) |
| `tl.range` vs `range` | loop construct | both wrong in the full kernel; both fine standalone |
| softmax on known S | `tl.max`/`tl.exp`/`tl.sum` on loaded S | **exact** (6e-8) |

Every piece was exact **in isolation**, but the **combination** (loads with
scalar base offsets + many programs) was wrong. The turning point was a
per-tile breakdown.

## 3. The minimal repro

```python
import torch, triton, triton.language as tl

@triton.jit
def fma_noexp(q_ptr, k_ptr, p_ptr, sq, sk, d, scale, H, BM: tl.constexpr, BN: tl.constexpr):
    pid = tl.program_id(0)
    bid = pid // H; hid = pid % H
    rm = tl.arange(0, BM); rn = tl.arange(0, BN)
    base_q = bid * sq * H * d + hid * d
    base_k = bid * sk * H * d + hid * d
    S = tl.zeros((BM, BN), dtype=tl.float32)
    for kk in range(0, d):
        qc = tl.load(q_ptr + base_q + rm * d + kk)   # (BM,)
        kc = tl.load(k_ptr + base_k + rn * d + kk)   # (BN,)
        S += qc[:, None].to(tl.float32) * kc[None, :].to(tl.float32)
    S *= scale
    tl.store(p_ptr + pid * sq * sk + rm[:, None] * sk + rn[None, :], S)
```

No `tl.dot`, no `exp`, no softmax — just scalar-offset loads accumulated in a
loop. Launch with **16 programs** (`bs*h` = 2×8) over an 8×8×128 problem:

```
pid=6  err=3.98    pid=7  err=3.69    pid=8  err=2.72    pid=9  err=3.06
pid=10 err=2.78    pid=11 err=2.96    pid=12 err=4.06    pid=13 err=3.81
pid=14 err=3.15    pid=15 err=4.56
```

- **pids 0–5 load q/k correctly; pids 6–15 load WRONG data** (deterministic).
- **Deterministic** across runs (identical wrong tiles).
- A trivial 8-program kernel (`store(x_ptr+pid)`) is **exact** — so it is not a
  bare `program_id` launch bug; it appears only with the load pattern.

## 4. Root cause

The **MUSA Triton backend deterministically miscompiles load addresses for a
subset of programs** when the kernel uses batched/headed scalar base offsets
(`base = bid * stride_b + hid * stride_h`) inside a loop. The wrong-program
threshold depends on kernel structure and program count (it moved between the
2D-grid and flat-grid variants), consistent with a warp/lane-to-program
assignment bug in the vendor codegen — not a data race (deterministic).

Consequence: any Triton flash-attention (which is exactly this pattern, at
many programs) on MUSA produces data-dependent wrong outputs. The same ~2.9
signature appears on Enflame GCU300 (§E2E-REPORT 2.6.1) and is likely the same
class of address/lane miscompile in its `make_gcuir` backend (Enflame has
additional independent issues: int64 rejection, flash-attn ABI).

## 5. Impact

- **flag_gems `flash_attn_varlen_func`** (and any flash kernel) on MUSA: wrong
  outputs → vllm inference garbage.
- Basic ops (`mm`, `add`, `silu`) via torch are unaffected; torch's own matmul
  is exact on MUSA.
- The flag_gems kernel logic is **correct** — verified piece-by-piece. The bug
  is in the vendor compiler's address/lane lowering.

## 6. Constructive next steps

1. **Report to the MUSA/mthreads toolchain team** with the minimal repro above
   (16-program FMA loop, pids 6+ load wrong addresses). This is a vendor
   compiler bug; flag_gems cannot fix it in-kernel.
2. **Flag for Enflame (GCU300)**: same ~2.9 signature — open a parallel
   report to Enflame's Triton backend team (`make_gcuir` address/lane
   lowering).
3. **flag_gems workaround (evaluation only, not committed)**: none is reliable
   yet — flattening the grid did not fix it. A single-program-per-lane
   restructure was not tried; if a robust workaround is needed before the
   vendor fix, that is the next experiment (force all tiles through one
   program with an inner head loop). Not recommended long-term.

## 7. Files / artifacts

- Probe scripts (repro + isolation chain) were run in a disposable container
  on the `mthreads` node and removed after use. The minimal repro above is
  self-contained.
- E2E-REPORT.md §2.3 (mthreads) and §2.6.1 (enflame) record the same ~2.9
  symptom from the vllm verification side.
