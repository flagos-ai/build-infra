---
title: "vllm0.24.0-arm64-triton3.7.2"
---

<!--
 Copyright 2026 FlagOS Contributors

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
-->

## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Arm Cortex-A720 / Cortex-A520 (Armv9, 12 cores)
- **Host driver:** none — this is a pure CPU image, no accelerator driver or container toolkit is required
- **CPU features:** `sve2`, `svei8mm`, `i8mm`, `bf16` (used by the SVE2/I8MM lowering in FlagTree CPU)

## Image contents

### Python

3.11.13

### Application package

`vllm==0.24.0+cpu`

`vllm-plugin-fl==0.3.0`

### Component versions

| Component | Version |
| --- | --- |
| FlagGems | `v5.4.0` (`6ed2f390`) |
| FlagTree CPU | `v0.1.0` (`2c35990a`) |
| vllm-plugin-FL | `v0.3.0` (`f1052770`) |
| triton | 3.7.2 (backend: `cpu`) |
| torch | 2.11.0+cpu |

## Environment

All of the following must be set — the CPU backend does not auto-detect anything.

- `FLAGGEMS_VENDOR=arm` — **required**. FlagGems does not auto-detect a CPU vendor; without it `import flag_gems` raises `RuntimeError: No device were detected on your machine !`
- `TRITON_CPU_BACKEND=1` — enables the FlagTree CPU backend
- `VLLM_PLUGINS=fl` — activates the plugin; without it vLLM runs on its native path and FlagGems is never used
- `VLLM_CPU_KVCACHE_SPACE=1` — **required, otherwise the server refuses to start**. vLLM's CPU worker checks available memory against `0.92 × total`; on a 32 GiB machine the check fails with `Available memory on node 0 ... is less than desired CPU memory utilization (0.92, ...)`. Setting this variable makes the check step aside
- `TRITON_CACHE_DIR=/root/arm64-vllm024-test/.cache/triton-2c35990` — **keep this exact absolute path** (see below)
- `A720_CORES` / `OMP_NUM_THREADS` / `MKL_NUM_THREADS` — pin to the big cores; `0,1,6,7,8,9,10,11` on a CIX-class Armv9 SoC

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-arm64-triton3.7.2:2.2.0-0.3.0`

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-arm64-triton3.7.2:2.2.0-0.3.0
```

This image ships no default application entrypoint command, so the launch command must be given explicitly.

Interactive shell:

```bash
docker run --rm -it --network host $IMG bash
```

Serve a quantized model (W4A8 example):

```bash
docker run --rm -it \
  --network host \
  -v /path/to/models:/models \
  -e FLAGGEMS_VENDOR=arm \
  -e TRITON_CPU_BACKEND=1 \
  -e VLLM_PLUGINS=fl \
  -e VLLM_CPU_KVCACHE_SPACE=1 \
  -e TRITON_CACHE_DIR=/root/arm64-vllm024-test/.cache/triton-2c35990 \
  -e VLLM_CPU_OMP_THREADS_BIND=0,1,6,7,8,9,10,11 \
  -e OMP_NUM_THREADS=8 \
  -e MKL_NUM_THREADS=8 \
  $IMG \
  /root/arm64-vllm024-test/.venv/bin/vllm serve /models/MiniCPM5-2B-W4A8-arm-FlagOS-packed \
    --host 0.0.0.0 --port 18043 \
    --dtype bfloat16 --enforce-eager \
    --max-model-len 1024 --max-num-batched-tokens 1024 --max-num-seqs 1 \
    --generation-config vllm --distributed-executor-backend uni \
    --disable-log-stats --language-model-only
```

`--host 0.0.0.0` is needed if you want to reach the server from outside the container; use `127.0.0.1` with `--network host` otherwise.

> **Supported model contracts.** Two quantized checkpoints have been verified end-to-end,
> both from the `FlagRelease` organization on ModelScope:
> - **Packed W4A8-G128** (`MiniCPM5-2B-W4A8-arm-FlagOS`) — routed through the plugin adapter to FlagGems `w4a8_g128_linear` and the FlagTree CPU backend. **This is the path FlagOS actually accelerates.**
> - **Channel-wise W8A8** (`MiniCPM5-2B-W8A8-arm-FlagOS`) — routed to vLLM's native `CompressedTensorsW8A8Int8` → `CPUInt8ScaledMMLinearKernel`. This path is **native vLLM**; the plugin coexists with it but does not accelerate it.

## Caching and first-run latency

Triton compiles kernels at runtime, and on the CPU backend the first compilation of the
W4A8 decode/prefill kernels takes a long time.

| Phase | Measured |
| --- | --- |
| Model initialization (cold) | 167.8 s |
| **First request, cold cache** | **888 s (≈ 15 minutes)** |
| Second request, same process | 0.303 s |
| **First request, same cache path** | **0.414 s** |

This image ships a **pre-warmed cache** at
`/root/arm64-vllm024-test/.cache/triton-2c35990`, covering the short-prompt smoke path.

- Keep `TRITON_CACHE_DIR` at that **exact absolute path** — the cache index stores absolute child paths, so moving it makes the cache useless (measured: a different path falls back to the full 906 s).
- The cache is **CPU-feature bound**. On a machine with different CPU features or a different compiler build, some kernels are compiled again; it still works, it just is not free.
- **Long-context and benchmarking paths are not pre-warmed** — the first such request may still spend minutes compiling.

## Known limitations

- **`logprobs` / `prompt_logprobs` are not usable on this backend.** Any request carrying either parameter makes vLLM compile a `topk_logprobs` Triton kernel sized by the vocabulary; on the CPU backend that compilation did not finish within 50 minutes, and while it runs the engine serves no requests at all — `/v1/models` stops responding too. Ordinary chat and completion requests are unaffected.
- W8A8 inference runs on vLLM's native CPU INT8 kernels, not on FlagOS operators (see above).
- This is single-user throughput. Concurrency and long-context behaviour are not covered here.
