# sglang-plugin-FL 零 sgl-kernel 可行性分析（2026-08-28）

## 背景与目标

per-backend 编译 sgl-kernel 的路线已叫停（见 `sglang-release-packaging-research.md`：
sgl-kernel 是 ABI 绑定二进制，随 (后端, python, torch) 变，逐个厂商要求提供编译件不现实）。
本文重新审视 sglang-plugin-FL 的设计，回答：**能否用 flag_gems 替换算子、完全不依赖 sgl-kernel？**

分析基线：
- sglang v0.5.10（`~/work/sglang-src`，HEAD 1519acf）
- sglang-plugin-FL 当前 HEAD（`~/work/sglang-plugin-FL`）
- FlagGems HEAD 1878e888f（`~/work/FlagGems`）

## 结论摘要

**可行，且 flagos 默认路径已经零 sgl-kernel。** 剩余工作是把 vendor backend 里
sgl_kernel / sgl_kernel_npu 的依赖迁移到 flag_gems，其中约 2/3 的 op 在 flag_gems 已有
覆盖，缺口集中在 enflame（gemma_rmsnorm / topk_sigmoid / causal_conv1d / merge_state_v2）
与 kunlunxin（klx_* 专用 kernel）。

| 层面 | 现状 | 结论 |
|---|---|---|
| sglang 本体（非 CUDA 平台） | MultiPlatformOp 落 forward_native + attention 默认 triton backend | 无硬依赖 ✅（metax E2E 已实证） |
| flagos backend（默认） | 6 op 全走 flag_gems.modules / flag_gems.fused | 已零 sgl_kernel ✅ |
| reference backend | 3rd 参考实现 | 零 sgl_kernel ✅ |
| vendor backend | hygon / enflame / kunlunxin / mthreads / tsingmicro / ascend 用 sgl_kernel | 需迁移，大部分有 flag_gems 覆盖，少部分缺口 |
| cuda backend | 用上游 sgl_kernel | NVIDIA 原生路径，不属本次范围 |

## 1. sglang 本体对 sgl_kernel 的依赖面

### 1.1 import 面

121 个文件 import sgl_kernel（91 非 test/bench：84 srt + 5 multimodal_gen + 2 jit_kernel）。
**仅 12 个文件有模块级无条件 import**，其余均在平台守卫下（is_cuda / is_hip / is_npu）或
函数内惰性 import。12 个文件全部是 CUDA / NPU 专用路径：

| 文件 | 顶层 import | 平台 |
|---|---|---|
| layers/attention/merge_state.py | merge_state_v2 | CUDA attention |
| layers/attention/flashmla_backend.py | flash_mla | CUDA MLA |
| layers/attention/flashattention_backend.py | flash_attn | CUDA |
| layers/attention/dual_chunk_flashattention_backend.py | flash_attn + sparse_flash_attn | CUDA |
| layers/attention/xpu_backend.py | sgl_kernel | XPU |
| layers/moe/cutlass_w4a8_moe.py | silu_and_mul | CUDA cutlass |
| layers/moe/fused_moe_triton/triton_kernels_moe.py | gelu_and_mul / silu_and_mul | CUDA |
| models/glm4_moe_lite.py | dsv3_router_gemm | CUDA |
| speculative/ngram_worker.py | reconstruct_indices_from_tree_mask | CUDA spec |
| hardware_backend/npu/attention/ascend_backend.py 等 3 文件 | sgl_kernel_npu | NPU |

### 1.2 启动可达性：attention backend 惰性选择

`attention_registry.py` 的 `create_*` 函数在**函数体内** import 各自 backend，注册表只是
名字→工厂。默认 backend 由 `server_args._get_default_attn_backend()` 决定：

```
MHA：hopper+cu12.3 → fa3；sm100 → trtllm_mha；HIP → aiter；MPS → torch_native；
     其余 → flashinfer（is_flashinfer_available()）否则 triton
MLA：hopper → fa3；sm100 → flashinfer；HIP → aiter；MPS → torch_native；其余 → triton
```

非 CUDA 平台 `is_flashinfer_available()` 恒 False → **默认落 triton backend**（纯 triton，
不 import sgl_kernel）。12 个无条件 import 文件因此**在非 CUDA 平台启动时不可达**。

### 1.3 torch.ops.sgl_kernel.* 调用清单

绝大多数是 CPU AMX 路径（`*_cpu`：rmsnorm_cpu、silu_and_mul_cpu、layernorm_cpu、
extend_attention_cpu、decode_attention_cpu、topk_softmax_cpu、grouped_topk_cpu、
fp8_scaled_mm_cpu 等）、IPC（shm_allreduce / shm_allgather）与 CUDA 守卫分支
（rotary_embedding、causal_conv1d_update）。非 CPU 调用全部位于 is_cuda / is_npu 分支内。

### 1.4 MultiPlatformOp 兜底

`layers/utils/multi_platform.py` dispatch_forward：未知平台 → forward_native；
forward_musa / forward_hpu 也 → forward_native。**任何未实现平台天然落 torch 原生实现，
不需要 sgl_kernel。** metax E2E 实证：无 sgl_kernel 时 F/T 双路径 serve + sampling 全过。

## 2. sglang-plugin-FL Layer 2 对 fused kernel 的覆盖

### 2.1 bridge 覆盖的 op 类

AROUND hook（`_make_dispatch_hook`）拦截 MultiPlatformOp.dispatch_forward，_BRIDGE_MAP
覆盖 7 类：SiluAndMul / RMSNorm / GemmaRMSNorm / RotaryEmbedding / MRotaryEmbedding /
TopK / UnquantizedFusedMoEMethod。无 bridge 的 op 原样返回 self.forward_cuda（bypass）。
FLA 算子走 monkey-patch（fla_patch.py）。

### 2.2 flagos backend（默认路径，priority 150）已零 sgl_kernel

| SGLang op | flagos impl | 底层 |
|---|---|---|
| silu_and_mul | flag_gems.modules.activation.gems_silu_and_mul | ✅ |
| rms_norm | flag_gems.modules.normalization.gems_rms_forward | ✅ |
| rotary_embedding | flag_gems.modules.rotary_embedding.gems_rope_forward | ✅ |
| topk | flag_gems.topk_softmax（显式 torch.empty） | ✅ |
| mrotary_embedding | sglang 自带 triton（forward_triton / forward_native） | ✅ 无 sgl_kernel |
| fused_recurrent_gated_delta_rule | flag_gems.fused.FLA.fused_recurrent_gated_delta_rule_fwd | ✅ |

### 2.3 vendor backend 的 sgl_kernel 依赖（迁移面）

sgl_kernel 引用仅存在于 `backends/vendor/`：cuda、hygon、enflame、kunlunxin、mthreads、
tsingmicro、ascend。

| backend | sgl_kernel op | flag_gems 覆盖 |
|---|---|---|
| hygon | rmsnorm / fused_add_rmsnorm / rotary_embedding | ✅ 已覆盖 |
| enflame | silu_and_mul / rmsnorm / gemma_rmsnorm×2 / topk_softmax / topk_sigmoid / fused_moe_kernel / moe_align_block_size / moe_sum / causal_conv1d / merge_state_v2 | ⚠️ 大部分覆盖，4 缺口 |
| kunlunxin | klx_gated_delta_net / klx_fused_experts / klx_attention_extend / causal_conv1d | ❌ klx 专用 kernel 无覆盖 |
| mthreads | gemma_rmsnorm / fused_add_rmsnorm | ⚠️ gemma_rmsnorm 缺口 |
| tsingmicro | moe_align_block_size（patch 绕过）+ platform_stubs | ✅ moe_align_block_size 已覆盖 |
| ascend | sgl_kernel_npu：swiglu_oai / add_gemma_rms_norm / chunk_gated_delta_rule_npu | ⚠️ chunk_gated_delta_rule 已覆盖，其余看 _ascend backend |
| cuda | 上游 sgl_kernel | NVIDIA 原生，不属范围 |

## 3. flag_gems 算子覆盖能力

### 3.1 ATen 注册面

`flag_gems.enable()` 注册除 exclude 清单外的全部 ops（ops/ 目录数百个 op：attention、
moe、norm、activation、elementwise 等）；支持 `only_enable(include=...)` 白名单模式。
sglang-plugin-FL `_setup_flaggems` 已接 USE_FLAGGEMS（默认 1）+ whitelist/blacklist。

### 3.2 fused/ 目录（与 sgl_kernel 直接对应的 kernel 级算子）

已确认存在：fused_moe_kernel（+ gptq_awq / dispatch_fused_moe_kernel /
invoke_fused_moe_triton_kernel）、moe_align_block_size、moe_sum、grouped_topk、
topk_softmax、silu_and_mul、add_rms_norm、rotary_embedding、chunk_gated_delta_rule、
FLA.fused_recurrent_gated_delta_rule_fwd、topk_softplus_sqrt、concat_and_cache_mla 等。

### 3.3 per-vendor backend 目录

runtime/backend/ 下已有 15 个厂商目录：_ascend / _metax / _hygon / _enflame /
_iluvatar / _kunlunxin / _mthreads / _nvidia / _cambricon / _sunrise / _thead /
_tsingmicro / _spacemit / _aipu / _amd。**flag_gems 设计上就是按厂商分发算子** ——
正是"每个厂商提供算子实现"而非"每个厂商提供 sgl_kernel 编译件"。

### 3.4 缺口清单（需自写 triton 或上游补充）

- gemma_rmsnorm（enflame / mthreads）
- topk_sigmoid（enflame）
- causal_conv1d（enflame / kunlunxin GDN）
- merge_state_v2（enflame flashattention patch）
- klx_* 专用 kernel（kunlunxin attention extend / gated delta net / fused experts）

## 4. 零 sgl-kernel 可行性评估

**结论：技术路线可行。** 论证链：

1. **sglang 本体不构成硬依赖**（§1）：非 CUDA 平台启动默认 triton attention backend，
   12 个顶层 import 全为 CUDA/NPU 专用文件且惰性可达；MultiPlatformOp 对未知平台落
   forward_native。metax E2E（无 sgl_kernel）已验证。
2. **默认路径已零 sgl-kernel**（§2.2）：flagos backend 6 op 全走 flag_gems；
   reference backend 零 sgl_kernel。
3. **迁移面可控**（§2.3 + §3）：vendor backend 的 sgl_kernel op 约 2/3 在 flag_gems
   已有直接对应（rms_norm / rotary / topk / fused_moe / moe_align / moe_sum / FLA）；
   缺口 4+3 个 op 可自写 triton 实现（tsingmicro 已有"绕过 sgl_kernel 用 triton"的先例）。

**收益**：不再依赖厂商提供 sgl_kernel 编译件；算子实现收敛到 flag_gems 单一依赖；
flag_gems 已内置 per-vendor 分发机制，与 sglang-plugin-FL 的 vendor backend 一一对应。

**风险与代价**：
- 性能：flag_gems triton kernel vs 厂商手写 kernel 的差距需逐后端实测（参考 hygon /
  metax 线的既有结论）；klx 等专用 kernel（attention extend）迁移成本最高。
- 缺口 op 需自维护 triton 实现，进入 flag_gems 上游或被 vendor 吸收前由我们兜底。
- sglang 升级会引入新 op，需要 Layer 2 bridge 同步扩展（sglang-plugin-FL 自身职责）。
- 量化路径（fp8 / w4a8）的 fused_moe 覆盖需按实际模型验证（fused_moe_kernel_gptq_awq
  已存在）。

## 5. 建议路线

1. **短期（已具备）**：flagos 作为默认路径直接使用，vendor 未接入或不想提供 sgl_kernel
   的厂商先落 flagos。
2. **中期**：按厂商逐个迁移 vendor backend 到 flag_gems —— hygon（rms_norm / rotary）
   与 tsingmicro（moe_align_block_size）迁移成本最低，可先做；enflame 补 4 个缺口 op。
3. **kunlunxin / ascend**：klx_* 与 sgl_kernel_npu 依赖最重，评估是否用 flag_gems
   对应 backend 覆盖，或维持 vendor 提供（如厂商已有编译件）。
4. 缺口 op 的 triton 实现按"进 flag_gems 上游"为目标写，避免长期 fork。

## 附：待决策

- 迁移工作是否立项、优先级（hygon / enflame 先行？）
- 缺口 op 的维护归属（flag_gems 上游 vs 我们的 patch）
- 性能验收口径（逐后端 F/T 双路径 E2E + 吞吐对比）
