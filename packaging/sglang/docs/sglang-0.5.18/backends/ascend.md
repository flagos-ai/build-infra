# sglang 0.5.18 — Ascend CANN 9.0.0 / CANN 8.5.0 验证记录

> **零 sgl_kernel_npu 路线实证**（用户定案：全后端统一 flag_gems 算子库，不构建
> 原生 sgl_kernel_npu）。E2E 揭示 shim `_Dummy` 对**真调用点**会崩
> `ValueError: not enough values to unpack` → 以插件层 torch-native 真实现覆盖
> 7 个 genuine 符号，F/T 双路径 E2E 全过；app 镜像已发布
> （`sglang0.5.18-ascend-cann9.0.0:2.1.2-0.1.dev1_g2e568482e`）。同路线第二个
> 后端 cann8.5.0 已在 §7 闭环（同一插件 PR #84 头 0f98ddc、`USE_FLAGGEMS=0`
> 基线，app 镜像 `sglang0.5.18-ascend-cann8.5.0:2.1.2-0.1.dev1_g0f98ddc20`）。

## 1. 环境

| 项 | 值 |
|---|---|
| 节点 / 容器 | hw25 `sglang-verify-ascend-cann9.0.0`（NPU 2 Health OK）|
| 镜像 | `flagos-runtime-ascend-cann9.0.0`（aarch64）|
| Python | 3.11 |
| torch | torch_npu（CANN 9.0.0）|
| sglang | 0.5.18+flagos（srt_empty 基座 wheel，aarch64）|
| sgl_kernel_npu | 共享 `sgl-kernel-shim` 0.5.18 内的 `sgl_kernel_npu` 磁盘级 stub 树（零原生算子；import 面见 §2.1）|
| sglang-plugin-FL | `sglang_fl 0.1.dev1+g2e568482e`（exp/0.5.18/ascend 分支 wheel，含 torch-native 真实现）|
| 模型 | Qwen3-4B（节点无 0.6B；同 qwen3 架构同内核路径）|
| flag_gems | 库技术路线已定，serve 时 `USE_FLAGGEMS=0`（flag_gems.enable() 污染 torch_npu，见 §5）|

## 2. 崩溃链定性（E2E 实证）

| 层 | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | serve 起不来 | flag_gems.enable() 污染 torch_npu | `USE_FLAGGEMS=0` |
| 2 | import 崩 | 0.5.18 无 `runner.hybrid_gdn_config` / `mambaish_config` | `getattr` 守卫（插件 commit e38d01f / c8a8421）|
| 3 | 首次 forward 崩 | shim `_Dummy.__iter__` 空迭代 → `ValueError: not enough values to unpack (expected 3, got 0)` | torch-native 真实现（§3）|
| 4 | KV cache OOB DDR（507035 MTE 异常）| shimmed `alloc_extend_kernel` no-op → `out_indices` 残留 garbage → 坏 `loc` 喂给 `_npu_reshape_and_cache` | `_AllocExtendKernel` trampoline → `alloc_extend_naive`（§3）|

### 2.1 sgl_kernel_npu import 面为什么必须磁盘级（2026-09-03 实证修正）

初版设想把 `sgl_kernel_npu` 名在插件 load_plugin 时 sys.modules 别名/seed 到
`sg_kernel` shim——**结构上不可行**：spawn 的 scheduler worker 在模块导入期
（scheduler.py → mem_cache → mha.py:65 `from sgl_kernel_npu.kvcacheio import
TransferDirection`）就 import `sgl_kernel_npu`，早于任何插件加载；load_plugin
自身的 step3（activation→quantization→layernorm）也早于 step5 patch。import 面
必须是**磁盘级包**（任何进程、任何时机可 import）。落法：`sgl_kernel_npu` stub
树（9 子包 48 叶子，E2E 权威清单）并入共享 `sgl-kernel-shim` wheel
（addon generate.py `_write_tree`，同 `_Dummy` + 模块级 `__getattr__` 机制）；
仅 ascend 会 import 它，其余平台 inert。

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

## 4. E2E 验证（F/T 双路径，Qwen3-4B，NPU 5）

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

- **实证覆盖**：Qwen3-4B 走 `split_qkv_rmsnorm_rope`（变体 1）+ `alloc_extend_kernel`
  两路，F/T 双路径全过（app 镜像 serve 3×200/ct=144 复核）。变体 2/3/4
  （qwen3_next、llada2/minimax_m3、minimax_m2）按各模型 native forward_prepare
  语义推导实现，**未实证**——换模型时按同法补跑。
- 残留 `_copy_kernel` 间歇性问题（未复现）；`USE_FLAGGEMS=1` 组合未验证。
- 插件 ascend commit（torch-native 真实现 + §2.1 import 面落法）已在
  exp/0.5.18-ascend（PR #84）；shim 的 npu stub 树在共享 addon（exp/0.5.18）。

## 7. cann8.5.0（2026-09-07；同一插件 PR #84 头 0f98ddc，flag_gems OFF 基线）

第二个 ascend 后端走 §1–§6 同一条零 sgl_kernel_npu 路线：同一共享
`sgl-kernel-shim` wheel（§2.1 import 面落法）+ 插件 torch-native 真实现（§3），
E2E 差异全在工具链与 flag_gems 取舍。flag_gems 处置按用户定案走两级：先在插件
yaml 逐算子屏蔽（用户否决 #775 旧方向 "Ascend 的这种完全屏蔽 flaggems 的方式
不可接受"，须逐个算子屏蔽），逐算子清完崩溃后吞吐仍病理 → 最终跟随背书基线
（cann9.0.0）`USE_FLAGGEMS=0`。§7 的 21-op blacklist 不因 OFF 失效：flag_gems-ON
语义下正确（清全部 crash/compile-error），保留作文档/防护，serve 时 inert。

| 项 | cann8.5.0（本段）| cann9.0.0（§1–§6）|
|---|---|---|
| 节点 / 容器 | hw26 `sglang-verify-ascend-cann8.5.0` | hw25（NPU 2 Health OK）|
| torch | torch_npu（torch 2.9.0+cpu + torch-npu 2.9.0，CANN 8.5.0）| torch_npu（CANN 9.0.0）|
| driver | 25.5.0 | 26.0.rc1 |
| flagtree（F）| 0.6.0+ascend3.2 | 0.6.1+ascend3.5 |
| vendor triton（T）| triton-ascend 3.2.0 | triton 3.5 / triton_ascend 3.2.1 |
| flag_gems | 5.3.5（serve 时 `USE_FLAGGEMS=0`）| 5.3.5（同）|
| sglang_fl | `0.1.dev1+g0f98ddc20`（exp/0.5.18/ascend）| `0.1.dev1+g2e568482e`（同分支较早头）|
| 模型 | Qwen3-4B | Qwen3-4B |

**flag_gems 病理两级实证**（A/B 同环境，先逐算子屏蔽后整体 OFF）：

| 层 | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | serve 在 Qwen3-4B 权重装载期崩 | `torch.__rpow__` → flag_gems ascend `pow_scalar` → `CompilationError 27:15 UnsupportedLanguageConstruct`（pow.py 的 fp32/fp16/bf16 分支用链式 constexpr `(A or B or C)` 守卫，flagtree 0.6.0+ascend3.2 拒编该 AST；cann9.0.0 的 0.6.1+ascend3.5 不撞）| ascend.yaml `flagos_blacklist` += pow 族五名（pow_scalar + 四个 aten dispatch 变体）+ `lift_fresh` |
| 2 | 21-op 屏蔽后 serve 构造全绿，吞吐仍 ~10000× 病理 | AICore ~83% 满磨但无具名 kernel（decode 0.05 tok/s）；已无离散算子可再屏蔽；同环境仅 `USE_FLAGGEMS=0` → READY 134s + decode 10.2 tok/s（vs ON 525s + 0.05）= flagtree 0.6.0+ascend3.2 codegen 效率缺陷 | 用户定案 `USE_FLAGGEMS=0`（env.app.sglang，#775 merged 1905cf1，英文 why 注释引实测）|

**blacklist 21 项**（全套与英文 why 注释见插件 ascend.yaml @0f98ddc；命名匹配
flag_gems `GeneralOpRegistrar.config_filter` 按注册 dispatch fn `__name__` 排除，
env `SGLANG_FL_FLAGOS_*` 会整体覆盖 yaml，勿用）：
`full_like, index_copy_, gather, count_nonzero, index_put_, _index_put_impl_,
cumsum, fill_scalar_, argmax, index, add_, conv1d, floor_divide, true_divide_,
addmm, pow_scalar, pow_tensor_scalar, pow_tensor_scalar_, pow_tensor_tensor,
pow_tensor_tensor_, lift_fresh`。后六项为 cann8.5.0 新增（pow 族回退 torch_npu
无损；`lift_fresh` 经 torch.empty_like 落 `_copy_kernel` coreDim=0 EE1003），
cann9.0.0 交付镜像（`g2e568482e`）仍是 15 项基线；21 项在 flag_gems-ON 语义下
清全部 serve crash/compile-error（run-3 serve 构造全绿）。

**E2E（F/T 双路径，Qwen3-4B，判据同 §4）**：正式输出 hw26
`/home/secure/sglang-verify-cann850-{F3,T}-formal.log`（harness head == merged
main 1905cf1，含 #775 env.app.sglang）；serve env `USE_FLAGGEMS=0` → 日志
"FlagGems disabled"。

| 路径 | 编译器 | readiness | decode | 结果 |
|---|---|---|---|---|
| F | flagtree | ~140s | ~10.3 tok/s | ✅ 3/3 |
| T | vendor triton | ~140s | 9.5–10.1 tok/s | ✅ 3/3 |

**交付**：app 镜像 `sglang0.5.18-ascend-cann8.5.0:2.1.2-0.1.dev1_g0f98ddc20`
已发布（app-image workflow verify 在 hw26 复核 serve E2E；record PR #780 merged
5261cce 已入 status_matrix image_tag）。节点已净（容器/脚本全清，他人残留未动）。

## 8. 外部线索（未实测，待 flag_gems-ON 窗口验证）

- **`index_select` 黑名单提效（2026-09-07 其他团队反应）**：ascend 上把
  `index_select` 加进 `flagos_blacklist`（插件 ascend.yaml）可有明显性能提升，
  我方未实测。适用前提 = flag_gems ON（cann9.0.0 交付与 cann8.5.0 配置均为
  `USE_FLAGGEMS=0`，此线索 inert）。测法：yaml `flagos_blacklist` 单加
  `index_select`（env `SGLANG_FL_FLAGOS_*` 会整体覆盖 yaml，勿用），起 serve
  对比 tok/s 与 AICore。命中则按本文件 §5/#1 同款英文 why 注释固化。
