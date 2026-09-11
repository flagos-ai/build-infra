# sglang 0.5.18 — Sunrise TANGRT 1.2.0 验证记录

> **2026-09-11 验证通过（F/T 双路径）**。sunrise 的 torch 是 `+cpu` 构建 + PTPU 设备，
> **不是 CUDA-alias**（`torch.cuda.is_available()` 为假）——插件此前承载的厂商都以
> True 回答，核心提前短路，所以两处只被非 CUDA-alias 平台走到的兜底缺陷直到这里才暴露。
> 修复在 sglang-plugin-FL PR #103。

## 1. 环境

| 项 | 值 |
|---|---|
| 节点 | sunrise（SR-SUN-S2-X1，8 卡）|
| 镜像 | `flagos-runtime-sunrise-tangrt1.2.0:2.1.2` |
| Python / torch | 3.10 / 2.11.0+cpu（`torch-ptpu==0.2.3+torch2.11`）|
| flagtree / vendor triton | 0.6.0+sunrise3.6（F）/ 3.6.0.1+git0a5cfb35（T）|
| flag_gems | **5.3.6** |
| sglang / 插件 | 0.5.18+flagos / `0.1.dev1+g3b94dae1f`（PR #103）|
| 模型 | Qwen3-4B（节点无 0.6B）|

## 2. 修复链

| # | 阻塞 | 归属 |
|---|---|---|
| 1 | flag_gems 5.3.5：import 崩（`nearbyint` / `asin`）+ 首个 prefill 崩（cumsum 空张量）| flag_gems **5.3.6** |
| 2 | `PlatformFL.get_device` 返回 `torch.device`，核心要字符串 | 插件 #103 |
| 3 | `_DIST_BACKEND_MAP` 无 sunrise → 默认 `nccl`，该栈只有 `pccl` | 插件 #103 |
| 4 | `compressed_tensors` 缺失 | `deps_app` |
| 5 | 两个 flag_gems 覆写不兼容 | 黑名单（§3）|

**为什么必须升到 5.3.6**：三条里两条在 `enable()` 之前触发，黑名单够不着 ——
F 路径 `ptpu.libdevice` 无 `nearbyint`；T 路径 `ops/arcsin.py:23` 模块级
`_tl_extra_shim.asin` 无 `asin`；第三条在首个 prefill，`compute_position_torch`
传 `extend_seq_lens[:-1]`，单序列下长度为 0 → `_sunrise/ops/cumsum.py` 除零。
三处都在 v5.3.6（asin 与 cumsum 守卫来自本线所提 FlagGems PR #6165）。

**两处插件缺陷**（#103）：`get_device` 返回类型（`server_args.py` 里
`self.device.split(":")` → `AttributeError`）与 dist backend 缺项
（`Distributed package doesn't have NCCL built in`）。都只在核心未命中加速器分支时
才被走到。`_ATTN_BACKEND_MAP` 也无 sunrise 条目 → 注意力落 `torch_native`（正确、慢），
本次不改。

## 3. 交付配置中的黑名单

黑名单是交付配置的一部分，不是调试残留：

| 算子 | 缺陷 | 上游 |
|---|---|---|
| `_scaled_dot_product_attention_math` | 不接受 `enable_gqa`，所有 GQA 模型首个 prefill 即死 | FlagGems #6172 |
| `pow_scalar` / `pow_tensor_scalar` / `pow_tensor_tensor` | `_fallback_pow` 在本平台 `scalar ** tensor` 失败 | FlagGems #6173 |

非 GQA 调用（head 数相等）走厂商 kernel，不受 #6172 影响 —— Qwen3-4B 是 32 q / 8 kv。

## 4. E2E 验证

判据：serve ready 后 3× chat/completions HTTP 200 + ct>0 + `sampling_backend=pytorch`。
**F 与 T 同一份配置**，唯一变量是编译器。

| 路径 | 编译器 | 结果 |
|---|---|---|
| F | flagtree 0.6.0+sunrise3.6 | ✅ ready ~50s，3/3，ct=144 |
| T | vendor triton 3.6.0.1 | ✅ ready ~50s，3/3，ct=144 |

app 镜像走正式链路（changelog 门禁 → 构建 → app 镜像 serve E2E → push）：
`sglang0.5.18-sunrise-tangrt1.2.0:2.1.2-0.1.dev1_g3b94dae1f`（digest `sha256:8bd68d0e…`）。

## 5. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | **F/T 必须同一份配置**（env、黑名单、参数），只有编译器不同。本轮一度给 T 多加三项 pow 黑名单，"双路径通过"即不成立 —— 已改并集重跑 F | 报告前 diff 两侧配置 |
| 2 | 探查黑名单是否生效**必须 `flag_gems.enable()`** —— 只 import 走原生路径，会误判成功 | 探查先 enable |
| 3 | `docker exec bash -c` 里 `pkill -f sglang.launch_server` 会杀死自己（命令行含该字面量）| 启动/停止分两次 exec |
| 4 | `--model` 必须显式传（节点无 0.6B，默认路径不存在）| dispatch 时带上 |

## 6. 遗留

- 插件 PR #103 待合入 `exp/0.5.18`。
- **flag_gems 漂移**：sunrise runtime 2.1.2 实为 5.3.6（按 workflow `flaggems` 入参
  单独重建以解除阻塞），而 `configs.yaml` 仍写 `5.3.5`。**按 configs 重建会静默退回
  5.3.5，sunrise sglang 再次崩在 import。** 解除 = 全栈 bump ≥5.3.6。
- FlagTree #1142 修复后移除 `deps_app` 的 `pytest`。
