# vllm 0.24.0 — kunlunxin xre5.37.1

> 本文对应原报告 §13。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 13. kunlunxin（XRE 5.37.1）详细记录（2026-08-23）

> 状态：**验证完成（2026-08-23）**。构建（cp310 empty wheel）、插件移植
> （PR #401 → 插件 wheel）、app 镜像 serve E2E 三线全通过；serve E2E 覆盖
> flagtree 默认 + triton 侧装双编译器（§13.6/§13.7）。

### 13.1 结论摘要

0.24.0 on kunlunxin **可行且已验证**：构建侧（cp310 empty wheel）与插件侧
（release-0.2 → main 移植）两条路径均已跑通，serve + 推理 E2E 通过——且与
0.20.2 线一致，flagtree 默认 + triton 侧装双编译器均可正常 serve 推理
（§13.6/§13.7）。
两处 0.24.0 结构性 API 变化（GDN 模块重构、fla.ops 平铺化）中，GDN 目标路径
已实测确认；attention 后端类接口经逐项比对基本兼容。遗留 FLA patch 目标路径
待重指（Qwen3-Next/GDN 前置，见 §13.4 与 [§14](../index.md)）。

### 13.2 构建侧：cp310 empty wheel

- pyproject 钉 `torch == 2.11.0`，但 `[tool.uv] no-build-isolation-package =
  ["torch"]` → 实际用 runtime 自带 torch（0.24.0 其余后端同法已验证）。
- kunlunxin 是 **python 3.10** → 需 **cp310 empty wheel**（0.24.0 wheel 绑定
  CPython 小版本，不能复用 cp312 产物，同 [sunrise §11.1](sunrise.md) 先例）。
- 单步安装维持 `--no-deps` → vendor torch 2.9.0+cu129 不被替换。
- ✅ cp310 empty wheel（vllm-0.24.0+flagos）已构建并上传（2026-08-23，
  vllm-wheel 工作流）；app 镜像单步安装线（§13.6）实测通过。

### 13.3 插件移植范围（main 目前零 kunlunxin 引用，全部从 release-0.2 @8236c0a 带回）

| 文件 | 内容 |
|---|---|
| `vllm_fl/dispatch/backends/vendor/kunlunxin/`（整目录） | kunlunxin.py + patch.py + register_ops.py + impl/* + patches/*（直接拷） |
| `vllm_fl/dispatch/config/kunlunxin.yaml` | main 缺此文件（按 platform 名自动加载） |
| `vllm_fl/utils.py` | VENDOR_DEVICE_MAP + supported_device 加 kunlunxin（device_type=cuda） |
| `vllm_fl/platform.py` | block_size=128 分支 |
| `vllm_fl/__init__.py` | `_patch_xpu_get_device` hook |
| `vllm_fl/ops/custom_ops.py` | `apply_kunlunxin_patches()` 调用 |
| `vllm_fl/ops/fused_moe/fused_moe_utils.py` | 3 处：TritonExpertsFL 恒用 + TRITON 回退 + patched fused_experts_impl |

### 13.4 0.24.0 API 适配点（已逐一验证）

| 变化 | 结论 |
|---|---|
| `mamba/gdn_linear_attn.py` 模块 → `mamba/gdn/` 包 | 三个 patch fn 需重指目标（名单见下） |
| fla.ops：chunk/fused_recurrent 子包 → 平铺模块 | 兼容；双层 patch（`_fla_ops_lib` + `_fla_chunk_lib`）原样可落 |
| `from vllm.distributed import get_tp_group` | ✅ 可解析（parallel_state 无 `__all__`，`import *` 带出 def@1349） |
| attention.py 类接口 | 兼容（细节见下） |
| `CommonAttentionMetadata` | ✅ backends/utils.py:37 再导出，无需改 import |
| `patch_attention_backend_registry`（CUSTOM 注册） | 死代码（dispatch 不经 enum）但 try/except 包裹，保留无害 |
| cudagraph | 0.24.0 有 `AttentionCGSupport`（backend.py:548）→ 可恢复（release-0.2 注释称 0.20.2 没有） |
| `patch_sampler_rng` 签名 | 0.24.0 以三位置参调用 `random_sample(probs, generators, use_fp64_gumbel)` → wrapper 需带 `use_fp64_gumbel=False`（f780db1，旧双参签名会 TypeError） |
| FLA 路径（实测） | `vllm/third_party/flash_linear_attention` 已不存在（仅剩 flashmla）；实为 `vllm/model_executor/layers/fla/ops` 平铺包（chunk.py / fused_recurrent.py） |

适配细节：
- GDN：三个 patch fn（patch_fla_ops / patch_fused_gdn_gating / patch_ssm_cache_update）需重指目标；
  0.24.0 引用方为 `mamba/gdn/qwen_gdn_linear_attn.py`（实测存在，`fla_chunk_gated_delta_rule`
  alias + `fused_recurrent_gated_delta_rule_packed_decode`）。
- fla.ops：0.24.0 模型新增 import `fused_recurrent_gated_delta_rule_packed_decode`。
  **实测缺陷**：patch.py 三个 FLA 目标仍指旧路径 `vllm.third_party.
  flash_linear_attention` → 0.24.0 上报 `Failed to patch FLA ops` /
  `Failed to patch _forward_core` 告警；Qwen3-4B（非 GDN）不受影响，但
  Qwen3-Next/GDN 的 chunk/fused_recurrent 替换会失效 → 验证前置修复
  （[§14](../index.md) 待办）。
- attention.py：`get_required_kv_cache_layout` 基类默认 None（backend.py:378）→ 0.24.0
  selector 无条件调用，兼容；`get_supported_head_size`（单数 static）需改名
  `get_supported_head_sizes`（复数 classmethod）对齐基类；`get_name()` 返回 "CUSTOM"
  合法无害。

### 13.5 验证风险清单（实测结果）

1. **torch 2.9.0+cu129 vs 0.24.0**（钉 2.11）—— ✅ 单步安装后 serve 启动、
   推理正常，同先例（hygon 2.9.0+das、mthreads、ascend）。
2. **cp310 empty wheel 首建** —— ✅ 构建通过并上传（首个非 cp312 的 0.24.0 wheel）。
3. **flag_gems flagos 路径** —— ✅ whitelist 生效（silu_and_mul / rms_norm /
   rotary_embedding）；op_backends 沿用 release-0.2 无需改。
4. **PR #400 alpha 修复**（patch.py:401）—— ✅ 0.24.0 路径生效（patched
   forward_decode 应用 + 推理无 NaN/乱码，§13.6）。
5. **triton 侧装编译器路径** —— ✅ 同一 app 镜像 `compiler triton`
   （/opt/triton，vendor triton 3.6.0+gitcd2d6c1b）serve E2E 通过，
   8 patches 全量应用、推理流畅，与 flagtree 路径输出可比（§13.7）。

### 13.6 验证记录（app 镜像 serve E2E，flagtree 路径，2026-08-23）

app 镜像（vllm empty wheel + 插件 wheel 单步安装线 + `vllm-serve` launcher）
在 kunlunxin P800 上的 serve + 推理端到端验证（默认编译器 flagtree 路径；
triton 路径见 §13.7）：

- 镜像 `harbor.baai.ac.cn/flagos-app/vllm0.24.0-kunlunxin-xre5.37.1:
  2.1.2-0.2.0_gf780db1.d20260823`（镜像 tag 中插件版本 `+`→`_`）
- 模型 `/data/models/Qwen3-4B`；serve：`vllm-serve --model
  /data/models/Qwen3-4B --port 8031 --served-model-name qwen3
  --reasoning-parser qwen3 --block-size 128 --gpu-memory-utilization 0.8
  --enforce-eager --trust-remote-code --max-model-len 2048 --dtype bfloat16`
- env（app 镜像 env.app.vllm 四变量，run 需显式 `-e`）：`VLLM_FL_PLATFORM=
  kunlunxin VLLM_FL_PREFER=flagos USE_FLAGGEMS=1 VLLM_FL_FLAGOS_WHITELIST=
  silu_and_mul,rms_norm,rotary_embedding`
- 版本指纹：vllm `0.24.0+flagos`（cp310 empty wheel）；vllm-plugin-fl
  `0.2.0+gf780db1.d20260823`；torch 2.9.0+cu129 / xtorch_ops
  0.1.2935+50a5d6a4 / flag_gems 5.3.4 / numpy 2.2.6 / python 3.10；
  fingerprint `vllm-0.24.0-92673996`
- 补丁全量应用（slot_mapping / attention registry / topk_topp / fused_moe /
  causal_conv1d / fused_gdn_gating / sampler RNG / decode attention），无
  patch_sampler_rng TypeError（f780db1 三参数签名生效）
- 推理：英文流畅；中文任务型 prompt（12/30/40/100 token）全流畅、无 NaN
  乱码、崩溃标记 0（100-token 长生成内容连贯，仅末尾小模型常规重复）
- ⚠️ FLA 补丁告警（非致命，Qwen3-4B 不受影响）：patch 目标仍指旧路径
  `vllm.third_party.flash_linear_attention`（0.24.0 已不存在），实为
  `vllm/model_executor/layers/fla/ops` → 待重指（§13.4 + [§14](../index.md)）
- ⚠️ 否定指令型 prompt（"不要用英文，不要用代码"）30-token 出"，，，"标点
  循环 —— 已证与 alpha 无关（同镜像同参数换任务型 prompt 即流畅，
  prompt 内容特性），记 [§14](../index.md) 观察项

### 13.7 验证记录（triton 路径 serve E2E，2026-08-23）

同一 app 镜像（§13.6），仅把编译器切换为侧装 triton 后重跑 serve + 推理，
确认双编译器在 0.24.0 上都可正常推理（与 0.20.2 线先例一致）：

- 容器 `compiler triton` 启动（默认 flagtree 换 triton）：PYTHONPATH 指向
  /opt/triton，`import triton` → **3.6.0**（vendor triton 3.6.0+gitcd2d6c1b，
  与 configs.yaml `triton:` 一致）
- serve 命令同 §13.6，仅 `--port 8032`（flagtree 线 8031），/dev/xpu3 +
  /dev/xpuctrl，env 四变量同
- 启动日志确认 8 个 plugin patches 全量应用，无 sampler RNG TypeError
  （f780db1 三参签名）
- 推理：同三个 completion prompt（1+1= / capital of France / 9.11 vs 9.9）
  输出流畅、无 NaN 乱码，与 flagtree 路径输出质量可比；chat 任务型 prompt
  （长生成）内容连贯
- ⚠️ FLA 补丁两告警同 §13.6（`vllm.third_party.flash_linear_attention`
  旧路径，0.24.0 已不存在）—— 非致命，Qwen3-4B 不受影响，待 [§14](../index.md) 重指
- 结论：flagtree（默认）与 triton（侧装）双编译器 serve E2E 均通过
