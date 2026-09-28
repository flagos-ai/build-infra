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

## Prerequisites（前置条件）

- **Architecture（架构）:** aarch64
- **Chip models（芯片型号）:** Arm Cortex-A720 / Cortex-A520（Armv9，12 核）
- **Host driver（宿主驱动）:** 无 —— 本镜像为**纯 CPU** 镜像，不需要任何加速卡驱动或容器工具包
- **CPU features（CPU 特性）:** `sve2`、`svei8mm`、`i8mm`、`bf16`（FlagTree CPU 的 SVE2/I8MM lowering 会用到）

## Image contents（镜像内容）

### Python

3.11.13

### Application package（应用包）

`vllm==0.24.0+cpu`

`vllm-plugin-fl==0.3.0`

### Component versions（组件版本）

| 组件 | 版本 |
| --- | --- |
| FlagGems | `v5.4.0` (`6ed2f390`) |
| FlagTree CPU | `v0.1.0` (`2c35990a`) |
| vllm-plugin-FL | `v0.3.0` (`f1052770`) |
| triton | 3.7.2（backend：`cpu`） |
| torch | 2.11.0+cpu |

## Environment（环境变量）

以下**全部必须设置** —— CPU 后端不做任何自动探测。

- `FLAGGEMS_VENDOR=arm` —— **必需**。FlagGems 不会自动识别 CPU 厂商；缺了会直接报
  `RuntimeError: No device were detected on your machine !`
- `TRITON_CPU_BACKEND=1` —— 启用 FlagTree CPU 后端
- `VLLM_PLUGINS=fl` —— 激活插件；不设则 vLLM 走原生路径，FlagGems 完全不参与
- `VLLM_CPU_KVCACHE_SPACE=1` —— **必需，不设服务起不来**。vLLM 的 CPU worker 会拿可用内存与
  `0.92 × 总内存` 比较；32 GiB 机器上该检查必然失败并报
  `Available memory on node 0 ... is less than desired CPU memory utilization (0.92, ...)`。
  设了此变量即可跳过该检查
- `TRITON_CACHE_DIR=/root/arm64-vllm024-test/.cache/triton-2c35990` —— **必须保持这个绝对路径**（原因见下）
- `A720_CORES` / `OMP_NUM_THREADS` / `MKL_NUM_THREADS` —— 绑到大核；CIX 级别 Armv9 SoC 上是 `0,1,6,7,8,9,10,11`

## Launch（启动）

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-arm64-triton3.7.2:2.2.0-0.3.0`

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-arm64-triton3.7.2:2.2.0-0.3.0
```

本镜像**不带默认应用入口命令**，启动命令必须显式给出。

进入交互式 shell：

```bash
docker run --rm -it --network host $IMG bash
```

起服务（以 W4A8 为例）：

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

若需从容器外访问，`--host` 用 `0.0.0.0`；仅在容器内访问则用 `127.0.0.1` 配合 `--network host`。

> **支持的模型契约。** 已端到端验证两份量化 checkpoint，均来自 ModelScope 的 `FlagRelease` 组织：
> - **Packed W4A8-G128**（`MiniCPM5-2B-W4A8-arm-FlagOS`）—— 经插件适配器路由到 FlagGems 的
>   `w4a8_g128_linear` 与 FlagTree CPU 后端。**这条路径才是 FlagOS 真正加速的路径。**
> - **Channel-wise W8A8**（`MiniCPM5-2B-W8A8-arm-FlagOS`）—— 路由到 vLLM 原生的
>   `CompressedTensorsW8A8Int8` → `CPUInt8ScaledMMLinearKernel`。**这条是 vLLM 原生路径**，
>   插件与它共存但**不参与加速**。

## Caching and first-run latency（缓存与首次运行延迟）

Triton 在运行期编译 kernel，而 CPU 后端上首次编译 W4A8 的 decode/prefill kernel 耗时很长。

| 阶段 | 实测 |
| --- | --- |
| 模型初始化（冷） | 167.8 s |
| **首次请求（冷缓存）** | **888 s（约 15 分钟）** |
| 同进程第二次请求 | 0.303 s |
| **首次请求（同缓存路径）** | **0.414 s** |

本镜像**预置了预热缓存**，位于 `/root/arm64-vllm024-test/.cache/triton-2c35990`，
覆盖短 prompt 的冒烟路径。

- 请把 `TRITON_CACHE_DIR` 保持在**该绝对路径** —— 缓存索引里存的是**绝对子路径**，
  换路径即完全失效（实测：换路径后回落到完整的 906 s）。
- 缓存与 **CPU 特性绑定**。在 CPU 特性不同或编译器构建不同的机器上，部分 kernel 会重新编译；
  仍能运行，只是不再免费。
- **长上下文与 benchmark 路径未预热** —— 这类请求首次仍可能花数分钟编译。

## Known limitations（已知限制）

- **本后端上 `logprobs` / `prompt_logprobs` 不可用。** 任何带这两个参数的请求都会让 vLLM 去编译
  一个按词表大小展开的 `topk_logprobs` Triton kernel；在 CPU 后端上该编译 **50 分钟未完成**，
  且编译期间引擎**不处理任何请求** —— `/v1/models` 也不再响应。普通对话与补全请求不受影响。
- W8A8 推理走 vLLM 原生 CPU INT8 kernel，不是 FlagOS 算子（见上）。
- 本文性能为**单用户**吞吐，未覆盖并发与长上下文行为。
