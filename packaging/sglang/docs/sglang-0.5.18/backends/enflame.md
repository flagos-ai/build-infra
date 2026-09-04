# sglang 0.5.18 — Enflame tops1.10.6 验证记录

> **2026-09-04 验证通过（F/T 双路径）**。enflame vendor 层此前在 0.5.18 wheel
> 上**从未加载**（顶层 import 引用了 0.5.18 缺失的 API，整个模块 import 失败），
> 修复后 serve 阻塞链全通（sglang-plugin-FL PR #91）。

## 1. 环境

| 项 | 值 |
|---|---|
| 镜像 | `flagos-runtime-enflame-tops1.10.6:2.1.2` |
| Python | 3.12 |
| torch | 2.11.0+cpu + torch-gcu 2.11.0+3.8.20260713（PrivateUse1）|
| flagtree | 0.6.1+enflame3.6 @ `/opt/flagtree`（F 路径）|
| vendor triton | 3.6.0+1.0.20260821.cc.1.10.6 @ `/opt/triton`（T 路径）|
| flag_gems | 5.3.5 |
| sglang | 0.5.18+flagos（srt_empty 基座 wheel）|
| sgl_kernel | sgl-kernel-shim 0.5.18 |
| sglang-plugin-FL | exp/0.5.18-enflame 分支（PR #91，单 commit）|
| numpy | 1.26.4 |
| 模型 | Qwen3-4B（节点无 Qwen3-0.6B）|
| SDK | Enflame driver 1.10.6 / TOPS Runtime 1.10.6（Zixiao C200 / S60）|

## 2. 构建与安装

- 构建：`build-and-repack.sh enflame-tops1.10.6`，`+flagos` repack，上传
  `flagos-pypi-enflame`。
- 安装（vendor index + aliyun extra）：`sglang==0.5.18+flagos`
  `sgl-kernel-shim==0.5.18` `scipy<1.18`。
- **compressed-tensors 不需要**：enflame runtime 已带 `compressed-tensors`
  （enflame-modelopt 依赖），且非 CUDA-alias，quantization 链被 gate——与
  metax/ascend/cambricon 不同，deps_app 留空。

## 3. E2E 验证（F/T 双路径，2026-09-04）

判据：HTTP 200 + completion_tokens>0 + sampling_backend=pytorch，3×
chat/completions（Qwen3-4B，`sampling_backend=pytorch` 经 /server_info 确认）。

| 路径 | 编译器 | 结果 |
|---|---|---|
| F | flagtree 0.6.1+enflame3.6 | ✅ 3/3 全过（completion_tokens=144）|
| T | vendor triton 3.6.0 | ✅ 3/3 全过（completion_tokens=144）|

> 冷启动慢：triton prefill kernel 每次编译 ~20s，decode 3-7 tok/s——verify
> 需长 `--serve-timeout`。

## 4. 代码改动（sglang-plugin-FL PR #91）

enflame vendor 层在 0.5.18 上**从未生效**：`patch.py` 顶层 import 引用
sglang dev-only API（`get_attention_tp_size` / `breakable_cuda_graph` /
`layers.attention.fla`，0.5.18 全无）→ 模块 import 失败 → `_apply_vendor_patches`
报 "vendor patch absent"，零补丁应用。之前所有 enflame 验证结论都建立在
vendor 层未生效的前提下，本次修复后才真正过。

| 改动 | 内容 |
|---|---|
| `patch.py` 重写 | 顶层 import 改为逐子模块 `importlib` + ImportError guard——一个漂移模块不再杀死整个 vendor 层 |
| `patches/device_properties.py`（新）| `torch_gcu._C._GcuDeviceProperties.is_integrated = False`（类级注入）|
| `patches/flashattention_backend.py` | 回迁到 0.5.18 类契约（`server_args.tp_size`、`token_to_kv_pool` 挂 self、补 0.5.18-stock 默认属性）|
| 漂移子模块（vision / cuda_graph_runner / chunk_delta_h）| guard-skip——0.5.18 缺失 API，Qwen3 文本用不到 |

**is_integrated serve 阻塞链**：sglang 0.5.18 scheduler 无条件装
triton_load_watch 钩子，每次 kernel load 调 `get_available_gpu_memory` → 读
`props.is_integrated` → torch_gcu 别名 CUDA 但属性类缺该字段 → AttributeError
杀 scheduler（只捕获 RuntimeError）。类级注入 False 后过（离散 GCU 有独立
HBM，False 正确，走 mem_get_info 路径）。

**flashattention_backend 为何必需**：is_integrated 修后下一阻塞 = fa3 factory
SM 断言（`SM>=80`）；改走 stock FlashAttentionBackend 又死在 sglang 0.5.18
wrapper 的 "flash_attn only on sm90+"（GCU 非 sm90）。vendor FA rewrite 直调
GCU flash-attn build（`vllm_flash_attn`）绕过——故回迁必需。

## 5. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | vendor 层静默不加载（顶层 import 漂移）| patch.py 逐模块 guard（#91）|
| 2 | `is_integrated` 缺失杀 scheduler（F/T 同崩）| 类级注入 False（#91）|
| 3 | fa3 断言 SM>=80 拒绝 GCU | vendor FA rewrite 直调 GCU flash-attn（#91）|
| 4 | verify 脚本硬编码 `--network host` 与 enflame RUN_FLAGS 重复 | docker 拒绝启动（脚本缺陷，待修）|
| 5 | shim 默认值 bug → Step 3b 静默跳过 | 脚本缺陷，待修 |
| 6 | 容器内 github clone 不可达 | host clone + docker cp（脚本缺陷，待修）|

## 6. 遗留

- 三个漂移子模块（vision/cuda_graph_runner/chunk_delta_h）guard-skip 未回迁，
  相应功能 enflame 上不启用——若需多模态等再补。
- 冷启动慢、性能未优化。
- 验证容器已拆，节点净。
