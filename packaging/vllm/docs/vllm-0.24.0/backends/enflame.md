# vllm 0.24.0 — enflame tops1.10.6/tops1.9.10

> 本文对应原报告 §17。标准流程见 [`playbook.md`](../playbook.md)，决策见
> [`decisions.md`](../decisions.md)。0.20.2 线的方案与根因见
> [vllm-0.20.2/backends/enflame.md §2.6](../../vllm-0.20.2/backends/enflame.md)。

## 17. enflame（GCU300）详细记录（2026-09-03）

**方案：** vLLM 原生 FLASH_ATTN（FA2，厂商快内核）+ 厂商算子 + 单入口补丁
（[VPF #432](https://github.com/flagos-ai/vllm-plugin-FL/pull/432)，分支 `port/enflame-gcu300-v024`
→ `0.3.0-rc2`，17 files / +1775 −112）；0.2 线孪生 PR 为
[VPF #357](https://github.com/flagos-ai/vllm-plugin-FL/pull/357)。

**约束提醒（同 0.20.2 §2.6）：** GCU300 的 triton 后端（`make_gcuir` 的 PassManager）拒绝 64 位
数据类型——非前端 / FlagTree 问题。0.24.0 上的绕法见 §17.1。

**环境：**

- 镜像 `vllm0.24.0-enflame-tops1.10.6:2.1.2-0.2.1_g7c6758c.d20260903`
- 模型 Qwen3-4B，TP=1；serve 参数 `--max-model-len 4096 --enforce-eager --gpu-memory-utilization 0.6
  --trust-remote-code`，env `VLLM_PLUGINS=fl`
- 编译器：FlagTree（默认 `/opt/flagtree`）+ vendor triton（`/opt/triton`），`compiler` 函数切换
- python 3.12（cp312 empty wheel，同 iluvatar 先例）；`device_type=gcu` 而 `vendor_name=enflame`，
  两者不同名

### 17.1 移植路径（0.20.2 的五处修复在 0.24.0 上不复用）

0.20.2 落库时已标注：slot_mapping 与 fa_utils 的绑定耦合 vLLM v1 worker/attention 布局，须对齐
0.24.0 后重新推导。移植后的形态：

- **KV 写路径按 0.24.0 基线** —— [playbook §2](playbook.md) 第 5 点的 `forward_includes_kv_cache_update`
  修复（[VPF #421](https://github.com/flagos-ai/vllm-plugin-FL/pull/421)）是本移植的前提；本 PR 不重复处理该属性。
- **注意力走 vLLM 原生 FLASH_ATTN** —— `gcu.yaml` 的 `attention_backend` 首位仍是 `vendor:gcu`，但胜出
  实现返回原生 FA2 后端路径（`gcu.py` 的 `attention_backend()`）；`impl/flash_attn_backend.py` 把厂商
  `flash_attn.vllm_flash_attn.flash_attn_varlen_func` / `get_scheduler_metadata` 与 flag_gems
  `fused.reshape_and_cache_flash` 绑上 `fa_utils`，并强制 `is_flash_attn_varlen_func_available()` → True、
  `get_flash_attn_version` → 2。厂商 FA2 不接受 FA3/FA4 时代的 kwargs，故按 `inspect.signature` 白名单
  裁剪（丢掉 `dynamic_causal` / `mask_mod` / `aux_tensors`）。
- **算子分发落新增的 `gcu.yaml`** —— 配置文件按 **device_name** 命名（`gcu.yaml`），而平台名是
  `vendor_name`（enflame），故 `get_config_path` 增加 device_name 别名回退（以 `VENDOR_DEVICE_MAP`
  成员判断为门，因为 `get_platform_name()` 也会给出 `cuda` / `unknown` 这类非 vendor 名）；否则
  `op_backends` **和** `flagos_blacklist` 双双静默不加载。厂商算子由 `register_ops.py` 注册，`gcu.yaml`
  的 `vendor:gcu` 档位才可解析。
- **int32 化绕 64 位墙** —— `impl/slot_mapping.py` 以 on-device int32 重写 `BlockTable.compute_slot_mapping`
  （token→request 用 `searchsorted`，不用 `repeat_interleave`——后者在 GCU300 走 index_select，grid.y
  上限 255）；`bilinear_pos_embed.py` / `chunk_delta_h.py` / `fused_recurrent_packed_decode.py` 各自处理
  grid 上限。
- **`max_num_batched_tokens` 钳到 2047** —— `platform.py` 在 `vendor_name == "enflame"` 时钳位：GCU 的
  grid.x 上限 65535，Qwen 的 q_norm kernel grid 为 batch × 32，2048 token 的步长即 2048×32 = 65536 溢出。
- **采样替换 `random_sample`** —— torch_gcu 无 `Tensor.exponential_(generator=)`
  （`model_runner._dummy_sampler_run` 也会踩到），`sampler.py` 换成无 seed 的 `q.exponential_()` 版本。
  统计上等价，代价是**失去 per-request seed 可复现性**（torch_gcu 运行时不支持）。
- **补丁单入口** —— `gcu/patch.py` 的 `apply_gcu_patches()` 是全部 GCU 补丁的唯一入口，由
  `platform.py:import_kernels` 在 `device_type == "gcu"` 时调用；采样补丁也在此应用，不靠 import 副作用。

`gcu.yaml` 的 `flagos_blacklist` 共 11 项，全部在 0.24.0 上由现场失败换得、并各带成因注释：
`scaled_dot_product_attention`、`sub`、`sort` / `sort_stable`、`rsub_scalar` / `rsub_tensor`、`argmax`、
`add`、`zeros` / `zeros_like` / `zero_`（int64 墙与 argmax correctness 的根因见 0.20.2 §2.6.2）。
`silu_and_mul` 的厂商档位已在本 PR 删除——GCU 实现与 reference 逐字节相同，只会遮蔽后者。

### 17.2 验证（✅ F/T 双路径，2026-09-03）

| 路径 | 编译器 | 就绪 | 贪心（temp 0）| 采样（temp 0.8 / top_p 0.9）|
|---|---|---|---|---|
| F | FlagTree（`/opt/flagtree`）| `Application startup complete` | HTTP 200 | HTTP 200 |
| T | vendor triton（`/opt/triton`）| `Application startup complete` | HTTP 200 | HTTP 200 |

贪心两路径输出 ` Paris. The capital of Germany is Berlin. The capital of Italy is Rome.`；采样两路径输出
连贯英文。算子分发两路径一致：

```
attention_backend   → vendor.gcu
rms_norm            → default.flagos
rotary_embedding    → default.flagos
silu_and_mul        → default.flagos
```

采样那一列才是真正压到黑名单与 `random_sample` 替换的：贪心走 `argmax`，不触发 top-k/top-p 的
`sort` / `rsub` 路径。替换后在 engine 内
`vllm.v1.sample.ops.topk_topp_sampler.random_sample` 即
`vllm_fl.dispatch.backends.vendor.gcu.sampler._random_sample_gcu`——补丁在启动期生效，不只是 import 期。

### 17.3 Stack

```
vllm:         0.24.0+flagos（cp312 empty wheel）        ✅  单步安装
vllm_fl:      VPF #432 分支 head                        ✅  F/T 双路径
app image:    vllm0.24.0-enflame-tops1.10.6
              :2.1.2-0.2.1_g7c6758c.d20260903           ✅
torch_gcu:    2.11 / tops1.10.6                         ✅
推理:         Qwen3-4B, TP=1, eager, HTTP 200           ✅
```

### 17.4 待办

- **tops1.9.10 待镜像重建后再验** —— 本轮 on-node 验证只在 tops1.10.6 上做。两栈制品同 tag
  `_g7c6758c.d20260903`，0.20.2 线已证同一份代码跨栈零改动（0.20.2 §2.6.2）；顶上不再单独重跑，
  随 app 镜像重建一并复验。
- **`fused_recurrent_packed_decode` 补丁在 0.24.0 上是 no-op** —— 两路径均报
  `import vllm.model_executor.layers.mamba.gdn_linear_attn` 失败（0.24.0 该模块路径已变），补丁被自身
  try/except 吞掉。不影响 Qwen3-4B；走 GDN 混合架构模型前需按 0.24.0 的模块路径重指向。
- **graph 模式未验** —— 本轮仅 eager；`platform.py` 的 `support_static_graph_mode()` 白名单不含 enflame。
  0.20.2 §2.6.3 记录的三个厂商侧阻塞（combo_kernels codegen wrapper、`persistent_reduction_configs`
  签名漂移、GCU300 64 位校验器无法从 serve 关闭）在 0.24.0 上是否同样存在，未复验。
- **flag_gems gcu300 argmax 内核缺陷仍在** —— 生产修复是黑名单（argmax → torch_gcu，根因见 0.20.2
  §2.6.2 结论 3），修好后可从 [VPF #432](https://github.com/flagos-ai/vllm-plugin-FL/pull/432) 移除 `argmax`。
- **加密采样**（`exponential_(generator=)`）未验，取舍见 §17.1。
