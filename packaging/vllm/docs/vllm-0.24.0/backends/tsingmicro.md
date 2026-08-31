# vllm 0.24.0 — tsingmicro tsm260610

> 本文是 tsingmicro 的首条验证记录（0.20.2 线未验证过该平台）。
> 标准流程见 [`playbook.md`](../playbook.md)，决策见 [`decisions.md`](../decisions.md)。

## 15. tsingmicro（TSM 260610）详细记录（2026-08-31）

**平台:** TsingMicro TX8110（tsm 节点，32 芯片）　**SDK:** TSM Runtime 260610164501

**目标:** vllm 0.24.0 (empty) + vllm-plugin-FL 的 **runtime 镜像**端到端验证，
`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm260610:2.1.2`

**结论：** F/T 双路径均 E2E 通过（5/5 prompts 一致）。0.24.0 核心阻塞点 =
vLLM 0.24 KV 缓存写入流程变更：`Attention.forward` 在调
`unified_attention_with_output` 前单独调 `unified_kv_cache_update`，调用
gate 是后端类的 `forward_includes_kv_cache_update`（True 则跳过写缓存）。
`AttentionFLBackend` 继承 vLLM 默认值 True → KV 缓存永不写入、forward 读零 →
全平台乱码（本后端首次暴露）。修复 = 两个后端类均覆盖为 False（
[PR #421](https://github.com/flagos-ai/vllm-plugin-FL/pull/421)）。TX8110 上
flag_gems attention 内核（`flash_attn_varlen_func` / `reshape_and_cache_flash`）
静默算错（probe maxrel=inf/nan/37.7），故新增 `TxdaSDPAAttentionBackend`：
复用 flag_gems metadata 机制（KV layout、block table、slot mapping）但以
torch SDPA 计算 attention、plain indexing 写 KV cache —— 两者 TX8110 上
数值正确。

**阻塞点（全部已解）：**

1. **KV 缓存永不写入（跨平台根因）** —— `forward_includes_kv_cache_update`
   继承 True；vLLM 全部 9 个官方 v1 后端都覆盖为 False，`AttentionFLBackend`
   无覆盖 → 乱码。修复见 [PR #421](https://github.com/flagos-ai/vllm-plugin-FL/pull/421)。
2. **flag_gems attention 内核 TX8110 静默算错** —— `flash_attn_varlen_func`
   probe maxrel=inf/nan/37.7；`reshape_and_cache_flash` 同样不可用 →
   走 `TxdaSDPAAttentionBackend`（torch SDPA + plain indexing）。
3. **advanced indexing 回退 CPU 挂起** —— `key_cache[blocks]`（list 索引）
   在 txda 上无 PrivateUse1 kernel → 回退 CPU copy 整个 cache，引擎级挂死；
   改 per-block slice + cat（probe 验证）。
4. **padded slot 写穿** —— profile 期 `slot_mapping == -1`，
   `-1 // block_size == -1` 会写最后一个 block；加 `slot_mapping >= 0`
   guard（运行时确认 profile 期 slot0=-1 正确跳过）。

### 15.1 环境指纹

- 镜像 `flagos-runtime-tsingmicro-tsm260610:2.1.2`；模型 `/data/models/Qwen/Qwen3-4B`
- python 3.10.20 / torch 2.11.0+cpu / torch_txda 0.1.0+20260728 / flag_gems 5.3.5
- vllm `0.24.0+flagos`（cp310 empty wheel，单步安装）；vllm-plugin-fl
  `0.3.0rc0+gbd010ce.d20260831`（PR #421 head 构建；tsingmicro PyPI 上更早的
  wheel 全部缺 KV 写路径修复 `forward_includes_kv_cache_update`，不可用于 0.24.0）
- 编译器：flagtree 0.6.1+tsingmicro3.3（默认 `/opt/flagtree`，运行时
  `triton.__version__` 3.6.0）+ vendor triton
  3.6.0.post2026072919+git8f5b0609（`/opt/triton`），`compiler` 函数切换
- serve 参数（测试脚本 LLM API）：`dtype=bfloat16, enforce_eager=True,
  max_model_len=1024, gpu_memory_utilization=0.9, tensor_parallel_size=1,
  trust_remote_code=True, seed=0`
- op_backends（tsingmicro.yaml）：`attention_backend: [flagos, vendor]`
  （flagos 在 TX8110 不可用 → 自动 fallback `vendor.txda`）；`rms_norm`/
  `rotary_embedding: [reference, flagos]`（flag_gems kernels TX8110 数值
  错误 maxrel~7200）；`silu_and_mul` → `default.flagos`

### 15.2 F 路径（flagtree 0.6.1+tsingmicro3.3）

run10 完成（DONE 1888.2s EXIT=0）。5/5 prompts 正确：

| prompt | 输出 |
|---|---|
| The capital of France is | ` Paris. The capital` |
| The capital of Germany is | ` Berlin. The capital` |
| 2 + 2 = | ` 4, ` |
| The largest ocean on Earth is the | ` Pacific Ocean, which` |
| The capital of Japan is（seed 7, max_tokens 8） | ` Tokyo, but the government is in Kyoto` |

算子路由：`rms_norm`/`rotary_embedding` → `reference.torch`（kind=reference）、
`silu_and_mul` → `default.flagos`、attention → `vendor.txda`。KV 写入
验证：do_kv_cache_update 写入值 = forward 读出值逐字节一致（插桩确认，
profile 期 slot=-1 被 guard 跳过、generation 期 slot=16/64/... 正常）。

### 15.3 T 路径（vendor triton 3.6.0.post2026072919+git8f5b0609）

run11 完成（DONE 2620.8s EXIT=0，T 路径较 F 慢 ~40%）。5/5 prompts 输出与
F 路径逐条一致（同上表）。算子路由与 F 路径相同；KV 写入验证同样
逐字节一致（插桩 kv_update#399 写入 v0 = fwd#400 读出 out0 =
`[-0.0172119140625, 0.00872802734375, 0.011962890625, -0.05908203125]`，
generation 期 slot=64~68 正常）。
