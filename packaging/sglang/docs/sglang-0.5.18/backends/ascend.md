# sglang 0.5.18 — Ascend CANN 9.0.0 验证记录

> **零 sgl_kernel_npu 路线实证**（用户定案：全后端统一 flag_gems 算子库，不构建
> 原生 sgl_kernel_npu）。E2E 揭示 shim `_Dummy` 对**真调用点**会崩
> `ValueError: not enough values to unpack` → 以插件层 torch-native 真实现覆盖
> 7 个 genuine 符号，F/T 双路径 E2E 全过。

## 1. 环境

| 项 | 值 |
|---|---|
| 节点 / 容器 | hw25 `sglang-verify-ascend-cann9.0.0`（NPU 2 Health OK）|
| 镜像 | `flagos-runtime-ascend-cann9.0.0`（aarch64）|
| Python | 3.11 |
| torch | torch_npu（CANN 9.0.0）|
| sglang | 0.5.18+flagos（srt_empty 基座 wheel，aarch64）|
| sgl_kernel_npu | sgl-kernel-shim 0.5.18（sgl_kernel_npu import 面由插件 sys.modules 别名指向 sgl_kernel shim，零原生算子；见 §3）|
| sglang-plugin-FL | `sglang_fl 0.2.0rc0.post2.dev11+gb9e835e85`（exp/0.5.18/ascend 分支 wheel）|
| 模型 | Qwen3-0.6B |
| flag_gems | 库技术路线已定，serve 时 `USE_FLAGGEMS=0`（flag_gems.enable() 污染 torch_npu，见 §5）|

## 2. 崩溃链定性（E2E 实证）

| 层 | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | serve 起不来 | flag_gems.enable() 污染 torch_npu | `USE_FLAGGEMS=0` |
| 2 | import 崩 | 0.5.18 无 `runner.hybrid_gdn_config` / `mambaish_config` | `getattr` 守卫（插件 commit e38d01f / c8a8421）|
| 3 | 首次 forward 崩 | shim `_Dummy.__iter__` 空迭代 → `ValueError: not enough values to unpack (expected 3, got 0)` | torch-native 真实现（§3）|
| 4 | KV cache OOB DDR（507035 MTE 异常）| shimmed `alloc_extend_kernel` no-op → `out_indices` 残留 garbage → 坏 `loc` 喂给 `_npu_reshape_and_cache` | `_AllocExtendKernel` trampoline → `alloc_extend_naive`（§3）|

## 3. 符号盘点与落法（genuine vs import-only）

容器内 shim 表面符号分两类：Qwen3-0.6B E2E 实证**真被调用**（genuine）的 7 个，
其余（mamba/moe/decode kernel 等）为纯 import-only，`_Dummy` 静默 no-op 足够。

**落法**：插件层 `sglang_fl/dispatch/backends/vendor/ascend/patches/npu_kernel_stubs.py`
实现，`patch_npu_kernel_stubs()` 在 load_plugin 时（模型模块 import 前）把真函数
setattr 到 shim 子模块——模型文件 `if _is_npu: from sgl_kernel_npu.norm.xxx import ...`
的模块级 import 单点覆盖，不改 sglang 源文件。register 进
`patches/patch.py apply_ascend_patches()`。

| 符号 | 模块 | 调用模型 | 实现语义 |
|---|---|---|---|
| `split_qkv_rmsnorm_rope` | `sgl_kernel_npu.norm` | qwen3 / qwen3_moe / llama / dflash / glm4_moe | 统一签名覆盖 5 文件：`split → _per_head_rmsnorm（可选）→ _apply_rope`，3D k/v head 布局 |
| `split_qkvgate_gemma_rmsnorm_rope` | 同上 | qwen3_next / qwen3_5 | q+gate 拼接拆半（`view(num_heads,-1)→chunk`），gemma 风格 norm（weight 存 0，有效 1+weight），gate 保持 flat |
| `split_qkv_rmsnorm_rope_pos_cache_half_npu` | 同上 | llada2 / minimax_m3 | **两调用点签名不同**（位置 vs 关键字参数）已兼容：llada2 传 `qkv/positions/cos_sin_cache/q_size/kv_size/head_dim` + eps/权重；minimax_m3 传 `input_tensor/positions/cos_sin_cache/q_hidden_size/kv_hidden_size/head_dim` + `gemma_weight`/`rope_dim`/`cast_norm_to_bf16` |
| `split_qkv_tp_rmsnorm_rope` | 同上 | minimax_m2 | TP 变体；`tp_world>1` 时原生会 all-reduce variance，本实现不重现（单卡精确）|
| `alloc_extend_kernel` | `sgl_kernel_npu.mem_cache` | `NPUPagedTokenToKVPoolAllocator.alloc_extend` | Triton grid-subscript 调用点（`kernel[(bs,)](...)`）由 `_AllocExtendKernel` trampoline 接住 → `alloc_extend_naive`（paged.py 参考实现）|

**关键前提**：`_per_head_rmsnorm` 镜像模型侧 `apply_qk_norm`（per-head reshape、
float32 variance、rsqrt、weight、cast back）；`_apply_rope` 兼容 `(N,1,1,freq_dim)`
BSNH cache 切片与 `(N,freq_dim)` plain cache 两种 cos/sin 形态；k/v 3D head 布局是
`torch_npu._npu_reshape_and_cache` 硬要求（2D flat 会让 ATB op setup failed / 507035）。

## 4. E2E 验证（F/T 双路径，Qwen3-0.6B，NPU 2）

服务：`python -m sglang.launch_server`，`--mem-fraction-static 0.6
--trust-remote-code --disable-cuda-graph --disable-piecewise-cuda-graph`。

判据：HTTP 200 + completion_tokens=144 + sampling_backend=pytorch，3× chat/completions。

| 路径 | 编译器 | readiness（server_args→startup complete）| gen throughput | 结果 |
|---|---|---|---|---|
| F | flagtree（:30002）| ~29s | 5.94–6.29 tok/s | ✅ 3/3 |
| T | vendor triton（:30003）| ~31s | 5.74–6.03 tok/s | ✅ 3/3 |

> **方法论修正（与 metax-0.5.12 记录对齐）**：0.5.18 的 chat/completions 响应体
> **永不携带** `sampling_backend`（它是 ServerArgs 启动记录字段，非 per-request
> 字段），body-based 检查结构上永远得 None。实证点改为 `GET /server_info`
> （http_server.py 返回 `asdict(server_args)`）。

## 5. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | flag_gems.enable() 污染 torch_npu | serve env `USE_FLAGGEMS=0`；**当前算子全部 torch-native，`USE_FLAGGEMS=1` 组合路径未验证** |
| 2 | 0.5.18 无 hybrid_gdn_config / mambaish_config | `getattr` 守卫（commit e38d01f / c8a8421，attention_registry.py）|
| 3 | shim `_Dummy` 对真调用点空 tuple 崩溃 | §3 torch-native 真实现（npu_kernel_stubs.py）|
| 4 | shimmed `alloc_extend_kernel` no-op → garbage loc → OOB DDR | `_AllocExtendKernel` trampoline → `alloc_extend_naive` |
| 5 | `_copy_kernel` 间歇性问题（历史会话出现）| 本 E2E 未触达，未复现 |

## 6. 覆盖范围与残留

- **实证覆盖**：Qwen3-0.6B 走 `split_qkv_rmsnorm_rope`（变体 1）+ `alloc_extend_kernel`
  两路，F/T 双路径全过。变体 2/3/4（qwen3_next、llada2/minimax_m3、minimax_m2）按
  各模型 native forward_prepare 语义推导实现，**未实证**——换模型时按同法补跑。
- 残留 `_copy_kernel` 间歇性问题（未复现）；`USE_FLAGGEMS=1` 组合未验证。
- 插件 wheel 本地构建、未 push（exp/0.5.18/ascend 分支 5 commit 待网络恢复后
  push + PR 回 exp/0.5.18）。
