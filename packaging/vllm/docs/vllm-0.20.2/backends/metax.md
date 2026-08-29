# vllm 0.20.2 — MetaX maca3.7.2.1

> 本文对应原报告第 2 部分 §2.2（含 maca3.8.1.3 复验）。标准流程见
> [`playbook.md`](../playbook.md)，决策见 [`decisions.md`](../decisions.md)。

## 2.2 MetaX maca3.7.2.1（首个 empty 后端）

**日期:** 2026-07-28/31　**平台:** MetaX C550 (8×, 64GB)

**MACA:** 3.7.2.0, Driver 3.8.30

**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-metax-maca3.7.2.1:2.1.1`

首个 `empty` 构建后端。MetaX MACA 无 CUDA 扩展，走 `VLLM_TARGET_DEVICE=empty`
——编译不含硬件 kernel 的 vllm，硬件算子由 vllm-plugin-FL 的 metax vendor
backend + flag_gems 提供。repack 规则、间接依赖处理、plugin 安装与 §1 一致。

> **状态：端到端已完成 ✅**（2026-07-31）。在设备可见的 serve 容器里，
> `vllm serve Qwen3-4B`（TP=1, `--enforce-eager`, gpu-util 0.6）成功
> 启动并返回正确推理。

### Repack（empty）

```bash
cd /workspace/vllm
VLLM_TARGET_DEVICE=empty MAX_JOBS=64 \
  pip wheel --no-build-isolation --no-deps -w /tmp/empty .
# → vllm-0.20.2+empty-...whl（无 .so）
python3 packaging/script/repack.py /tmp/empty/vllm-0.20.2+empty-*.whl
```

empty 构建跳过了硬件后端，empty vllm 的 77 个间接依赖中只有 **2 个**在自身
METADATA 声明了 torch/triton（对比 [§2.1](nvidia.md) standard 构建更多）：

| 包 | 声明 |
|---|---|
| `compressed-tensors`==0.15.0.1 | `torch>=1.7.0` |
| `xgrammar`==0.2.3 | `torch>=1.10.0` + `triton` |

`repack_recursive()` 自动发现并逐一剥离、上传（[§1.3](../playbook.md)）。其他
间接依赖（transformers、safetensors、outlines_core…）仅在未激活的 extras 中
声明 torch，pip 不激活 extras，无需处理。

> **历史差异（已被 [§1.3](../playbook.md) 取代）：** 早期 MetaX repack 为绕过
> pip 平台匹配，做过两件已废弃的临时操作——(a) 去掉 `+empty` 后缀改回裸
> `0.20.2`；(b) 把 WHEEL Tag 从 `py3-none-any` **伪造**成
> `cp38-abi3-manylinux_2_35_x86_64`。[§5.1](../decisions.md) 已否定伪造 platform
> tag（声明不存在的 ABI，误导），标准做法是加 `+flagos` 并保留 `py3-none-any`。

### 安装

> **历史差异（已被 [§1.4](../playbook.md) 取代）：** 因为当时 repack 未把间接
> 依赖 pin 到 `+flagos`，`torch-2.8.0+metax3.7.2.0` 在 PEP 440 里排序低于
> Aliyun 的 `torch-2.11.0`，一步安装会触发 torch 降级，只能两步 `--no-deps`
> 锚定：
> ```bash
> pip install --no-deps --index-url "$VENDOR" vllm==0.20.2   # 锁 repacked
> pip install         --index-url "$ALIYUN" vllm==0.20.2     # 补 safe deps
> ```
> PR #280（递归 `+flagos` pin）之后此坑消失，单步即可（[§1.4](../playbook.md)）。
> mthreads 已实测验证单步安全（[§2.3](mthreads.md)）。

运行时依赖（vendor 为主）：

```bash
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" \
  torch==2.8.0+metax3.7.2.0 torchaudio==2.4.1+metax3.7.2.0 \
  torchvision==0.15.1+metax3.7.2.0 flash_attn==2.6.3+metax3.7.2.0torch2.8 \
  flagtree==0.6.1+metax3.6 triton==3.0.0+metax3.7.2.0 flag_gems==5.3.5 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.3 numpy==2.3.5
```

安装 vllm-plugin-FL —— 纯 Python，不设 `VLLM_VENDOR`（[§1.5](../playbook.md)）：

```bash
cd /workspace/vllm-plugin-FL && pip install --no-build-isolation -e .
```

### 阻塞点：`reshape_and_cache_flash` 算子（由 plugin-FL #333 修复）

empty wheel 不含编译的 `_C_cache_ops` C kernel。MetaX flash attn 后端在
`fa_utils.py` 把 `reshape_and_cache_flash` 直接绑定到
`vllm._custom_ops.*` → `torch.ops._C_cache_ops.*`，首次前向崩溃：

```none
AttributeError: '_OpNamespace' '_C_cache_ops' object has no attribute
'reshape_and_cache_flash'
```

早期尝试 #319（`_C_cache_ops` Triton fallback）**从未生效**——守卫
`hasattr(torch.ops, "_C_cache_ops")` 对惰性 `_OpNamespace` 恒真，且 metax
C550 已禁用 Triton。

**修复（[#333](https://github.com/flagos-ai/vllm-plugin-FL/pull/333)）：**
把 `reshape_and_cache_flash` 注册为一等 dispatch op：

- `flaggems/flaggems.py` — 新增 `FlagGemsBackend.reshape_and_cache_flash`，
  转发到纯 Triton 的 `flag_gems.fused.reshape_and_cache_flash`。
- `flaggems/register_ops.py` — 注册为 `default.flagos`（`_has_flaggems_op` 守卫）。
- `metax/impl/attention/utils/fa_utils.py` — 调用点改为
  `CachedOp("reshape_and_cache_flash")`，不再绑定 vllm 私有 C op。

留在 dispatch 抽象内（policy 驱动、可回退、厂商无关），不耦合 vllm 私有
`_C_cache_ops` ABI。#333 取代 #319（已关闭）。

### serve + 推理 —— ✅ 成功

```bash
export VLLM_FL_DISPATCH_DEBUG=1        # 打印 dispatch 选择，确认 default.flagos
vllm serve /data/models/Qwen/Qwen3-4B --port 8031 \
  --gpu-memory-utilization 0.6 --enforce-eager \
  --trust-remote-code --max-model-len 2048
# NCCL→MCCL 由 pynccl_wrapper patch 自动完成，无需额外 env
```

```json
{"choices":[{"text":" Paris. The capital of Germany is Berlin. The capital of Italy is Rome.",
  "finish_reason":"length"}],
 "usage":{"prompt_tokens":5,"completion_tokens":16,"total_tokens":21}}
```

前向日志确认算子走对路（无 `_C_cache_ops` / `_C.silu_and_mul` 报错）：

```
Op 'silu_and_mul' using 'default.flagos' (kind=flagos, vendor=None)
Op 'reshape_and_cache_flash' using 'default.flagos' (kind=flagos, vendor=None)
```

> **实测注意事项：**
> - MCCL communicator 冷启动很慢（~11 min，进程 15–25% CPU，看似 hang 实为
>   在跑），不要过早 kill。
> - 被 kill 的 engine 以 `VLLM::EngineCore` 残留（`pkill -f "vllm serve"`
>   匹配不到）占显存，导致下次误报 "Free memory < desired"——按 PID 或
>   `pkill -9 -f EngineCore` 清理。

### Stack 验证

```
torch:        2.8.0+metax3.7.2.0    ✅  from vendor PyPI (未降级)
torchaudio:   2.4.1+metax3.7.2.0    ✅
torchvision:  0.15.1+metax3.7.2.0   ✅
flash_attn:   2.6.3+metax3.7.2.0    ✅
flagtree:     0.6.1+metax3.6       ✅  默认编译器
triton:       3.0.0+metax3.7.2.0    ✅
flag_gems:    5.3.5                 ✅
vllm:         0.20.2                ✅  empty, repacked, vendor PyPI
vllm_fl:      installed             ✅  纯 Python + #333
MACA device:  ✅ 可见                mx-smi (C550 8×64GB)
vllm serve:   ✅ 启动成功            TP=1, enforce-eager, gpu-util 0.6
Inference:    ✅ 成功                Qwen3-4B, prompt=5 / completion=16
```

### Triton 路径（T）复验：flag_gems scalar 返回 bug（2026-08-25）

**运行时镜像:** `flagos-runtime-metax-maca3.7.2.1:2.1.2`（flag_gems 5.3.4）。
maca3.7.2.1-T 在 `vllm serve` 阶段崩溃，报 `EngineCore` 初始化失败（v1 引擎
吞掉真实子进程 traceback）。根因在 flag_gems `LibTuner` 与 triton 3.0.0
的基准接口不匹配，两层：

1. triton 3.0.0 的 `Autotuner._bench` 在 `use_cuda_graph=True` 时走
   `do_bench_cudagraph(..., return_mode="median")`，返回**标量** median，
   而非标准的 `(p50, p20, p80)` 三元组。
2. flag_gems `LibTuner` 默认 `benchmark_mode=REPLAY`，triton 3.0.x 分支跳过
   `resolve_benchmarker`，`super().__init__` 拿到 `use_cuda_graph=True`；
   其 `bench` 闭包 `for value in ret` 迭代标量 → `TypeError: 'float' object
   is not iterable`（libentry.py:997）。
3. 即使把标量包成单元素 list，flagtune BenchmarkCache v2 按 3 分位数存取
   （sql.py `p50, p20, p80 = benchmark`）→ `ValueError: not enough values to
   unpack (expected 3, got 1)`。

**修复（上游 FlagGems `1537bde93a8e` / PR #5375）：** 在 `bench` 闭包把标量
归一化为 `(ret, ret, ret)`，`benchmark_with_requested_quantiles` 同步归一化
（`isinstance(ret, (int, float))`）。该修复**不在**任何 ≤ v5.3.4 的 tag，
已进入每日构建 `5.3.5.dev20260825`（下载 wheel 确认含归一化代码）。

**验证（2026-08-25）：** 本地补丁 triton 3.0.x legacy 分支
`use_cuda_graph=False`（等效于上游归一化，让 `_bench` 走 `do_bench` 返回
三元组）后，`vllm serve` 稳定到 `serve_ready`（~145s），真实
`POST /v1/completions` 返回 `200 OK` —— T 路径 E2E 通过。**但这是补丁验证，
runtime 镜像（flag_gems 5.3.4）尚未含修复，见待办。**

**补验（2026-08-25）：** flag_gems **5.3.5** clean wheel（含 `1537bde93a8e`
归一化）发布后重建 `flagos-runtime-metax-maca3.7.2.1:2.1.2`，verify-driver
`--compiler triton` E2E 通过（serve ready + `200 OK` 真实 completion），不再
依赖本地补丁。F/T 双路径均 ✅，本 bug 固化完成。

### 待办

1. **plugin-FL #333** —— ✅ 已提，E2E 通过：`reshape_and_cache_flash`→flag_gems
   （`CachedOp`）
1. **plugin-FL #319** —— ✅ 已关闭：守卫恒真从不生效，被 #333 取代
1. **plugin-FL #325（`_maca`→F.silu/F.gelu）** —— ✅ 已关闭：empty wheel 上 dispatch
   不走 vendor 路径，实测不需要（仅 +cpu wheel 有意义）
1. **repack.py empty 支持 + 递归审计** —— ✅：PR #244 #247
1. **更大模型 / graph / TP>1** —— ⬜：仅测过 Qwen3-4B + eager
1. **FlagGems pyproject build-system.requires 加 `wheel==0.45.0`** —— ⬜
1. **flag_gems scalar 返回 bug 固化** —— ✅ 已固化：flag_gems 5.3.5 clean wheel
   （含 `1537bde93a8e`）已发布并重建 runtime 镜像，verify-driver F/T 双路径 E2E
   通过

### MetaX maca3.8.1.3（2026-08-25 复验）

maca3.8.1.3 是 MetaX 较新后端（driver 3.9.6 / MACA SDK 3.8.1.3，C550），
与 maca3.7.2.1 共用 §2.2 的 empty 流程与 plugin-FL #333，无需额外补丁。
堆栈版本不同，且 **triton 3.6.0 不受 scalar 返回 bug 影响**（该 bug 仅
triton 3.0.0 触发）：

```
torch:        2.10.0+metax3.8.1.0    ✅
torchvision:  0.25.0+metax3.8.1.0    ✅
flash_attn:   2.6.3+metax3.8.1.0torch2.10  ✅
flagtree:     0.6.1+metax3.6         ✅  F 路径（默认）
triton:       3.6.0+metax3.8.1.0     ✅  T 路径
flag_gems:    5.3.5                  ✅
```

**验证（2026-08-25）：** `flagos-runtime-metax-maca3.8.1.3:2.1.2`（flag_gems
5.3.5 重建后）verify-driver `--compiler flagtree` 与 `--compiler triton`
双路径 E2E 均通过（serve ready + `200 OK` 真实 completion）。image_tag
`2.1.2-0.2.1_g3bc66eb.d20260825`。
