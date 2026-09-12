# vllm 0.20.2 — tsingmicro tsm260610

> 本文对应原报告第 2 部分 §2.14。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.14 tsingmicro-tsm260610（TX8110：✅ F/T 双路径 E2E 通过，2026-09-12）

**平台：** Tsingmicro TX8110（tsm 节点，32 芯片）　**SDK：** TSM Runtime 260610164501

**目标：** vllm 0.20.2 + vllm-plugin-FL 端到端验证（runtime 镜像 + 单步安装 wheel）。

**结论：** F/T 双路径 serve + 推理端到端通过，两条路径对同一组锚点 prompt
给出逐字一致的输出，算子路由也一致。0.24.0 线上定案的 TX8110 处理方式
（attention 绕开 flag_gems 内核、`rms_norm` / `rotary_embedding` 走 reference）
在 0.20.2 上同样成立；另修掉三个 TX8110 特有的开销/正确性陷阱，修复前
decode 约 19 s/token。

### 2.14.1 TX8110 的处理方式

1. **flag_gems attention 内核在 TX8110 上静默算错**（`flash_attn_varlen_func`
   probe maxrel=inf/nan/37.7）→ 新增 `TxdaSDPAAttentionBackend`：复用 flag_gems
   的 metadata 机制（KV layout、block table、slot mapping），attention 用
   torch SDPA 计算、KV 用基础索引写入 —— 两者在 txda 上数值正确。
   与 [0.24.0 §15](../../vllm-0.24.0/backends/tsingmicro.md) 同路线。
2. **dispatch 配置**（`vllm_fl/dispatch/config/tsingmicro.yaml`）：`attention_backend`
   只列 `vendor`；`rms_norm` / `rotary_embedding` → `reference` 优先
   （这两个 flag_gems 内核同样静默算错，而 `strict: false` 只在抛异常时回退，
   算错不触发回退）；`silu_and_mul` → `flagos`。
   `flagos_blacklist` 屏蔽 `to_copy` / `copy` / `copy_` / `masked_fill`：
   TX8110 的 triton copy 内核在采样阶段 int32→int64 这类改 dtype 的 cast 上挂死。
3. **`platform.py` 补 `txda → tccl`** 的分布式后端映射。

0.24.0 线的跨平台根因（KV 缓存写入 gate `forward_includes_kv_cache_update`）
在 release/0.2 上已存在，本线无需重复处理。

### 2.14.2 TX8110 特有的陷阱（已修）

均因 txda 缺对应 kernel —— 不报错，只是极慢或路径错误：

1. **tensor-index 赋值写 paged KV cache** —— 整个 cache 绕主机内存一圈，写入
   1 行与 2048 行成本相同（284 MiB cache 上均约 166 ms），单此一项每个 decode
   step 即数秒；改走基础索引（`cache[block_id, offset] = row`，约 0.02 ms）。
2. **0-dim `Tensor.item()` 必崩** —— `RuntimeError: TXDA error:
   (txMemcpyAsync(...)) = Invalid parameters`；改用 `.tolist()`（0-dim 亦可）。
3. **非连续（strided）设备张量读带宽极低** —— `view[pid]` 223.74 ms vs 连续
   `cont[pid]` 2.75 ms（约 80×）；`torch.chunk(2, dim=-1)` 产出的正是 strided
   view，每层约 220 ms × 36 层。改一次性 `.contiguous()` 物化 cos/sin 两半并缓存。

另两处边界：block table 行被 padding 到 `max_model_len / block_size`（padded
项仍要付设备 op），按真实块数截断；profile 期 `slot_mapping == -1` 会被
`-1 // block_size == -1` 写进最后一个 block，加 `slot >= 0` guard。

### 2.14.3 环境

| 组件 | 版本 |
|---|---|
| Python | 3.10.20 |
| torch | 2.11.0+cpu |
| torch_txda | 0.1.0+20260728.f6fbdb71 |
| txops | 0.1.0+20260716.e94d9509 |
| numpy | 1.26.4 |
| vLLM | 0.20.2+flagos |
| vllm-plugin-fl | 0.2.1+g90ffdf0.d20260912 |
| flag_gems | 5.3.5 |
| FlagTree | 0.6.1+tsingmicro3.3（`/opt/flagtree`，运行时 `triton.__version__` 3.3.0）|
| vendor triton | 3.6.0.post2026072919+git8f5b0609（`/opt/triton`）|
| 设备 / SDK | Tsingmicro TX8110 / TSM Runtime 260610164501 |
| 模型 | `/data/models/Qwen/Qwen3-4B` |

serve 参数：`--gpu-memory-utilization 0.4 --enforce-eager --trust-remote-code
--max-model-len 2048`。

两条路径的算子路由相同：`attention_backend` → `vendor.txda`（`TxdaSDPAAttentionBackend`）、
`rms_norm` / `rotary_embedding` → `reference.torch`、`silu_and_mul` →
`default.flagos`。

### 2.14.4 待办

1. **插件改动落到 upstream `release/0.2`** ——
   [vllm-plugin-FL #489](https://github.com/flagos-ai/vllm-plugin-FL/pull/489)
   （OPEN；本轮验证所用 wheel `0.2.1+g90ffdf0.d20260912` 即该 PR head 构建）。
2. **app 镜像未构建、未发布** —— 本轮只做 runtime 侧 E2E，矩阵的 `deps_app` /
   `launch_docs` / `image_tag` 均未置位。
3. **两条路径的首请求都会打穿 300 s 客户端超时** —— 编译器 JIT 所致（warm 后
   正常返回），验证脚本需要放宽客户端超时，否则会把冷启动误判为失败。
