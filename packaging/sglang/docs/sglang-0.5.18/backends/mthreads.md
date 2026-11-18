# sglang 0.5.18 — MThreads musa5.2.0 验证记录

> **2026-09-05 验证通过（F/T 双路径 + app 镜像）**。mthreads runtime 用经典
> `torch_musa`（PrivateUse1、不 alias CUDA），而 sglang 0.5.18 的 MUSA 支持
> 按上游 torchada（CUDA-alias）栈写——四个 vendor 修复让 serve 端到端跑通
> （sglang-plugin-FL PR #92）。

## 1. 环境

| 项 | 值 |
|---|---|
| 镜像 | `flagos-runtime-mthreads-musa5.2.0:2.1.2`（重建含 torchvision fix，#731）|
| Python | 3.10 |
| torch | 2.9.1+musa5.2.0（torch_musa 2.9.1，PrivateUse1，不 alias CUDA）|
| flagtree | 0.6.1+mthreads3.6 @ `/opt/flagtree`（F 路径）|
| vendor triton | 3.6.0 @ `/opt/triton`（T 路径）|
| flag_gems | 5.3.5 |
| sglang | 0.5.18+flagos |
| sglang-plugin-FL | exp/0.5.18-mthreads（PR #92，单 commit 607b967）|
| 模型 | Qwen3-4B |

## 2. 修复链（PR #92，四个 vendor patch）

sglang 0.5.18 MUSA 支持假设 torchada（CUDA-alias），flagos runtime 用经典
torch_musa（无 CUDA alias、无 gpu_migration 层）——连环暴露四个阻塞，逐一
以插件层修复（follow tsingmicro/cambricon 现成模式，非 per-vendor 大定制）：

| 阻塞 | 修复 |
|---|---|
| `is_musa()` 只认 torchada → get_device 落平台返回 torch.device → server_args `.split(":")` 崩 | device_support：is_musa 接受 torch_musa；能力/count 查询路由 torch.musa |
| `init_cublas()` 硬编码 device="cuda"，torch_musa 无 alias → NotImplementedError | init_cublas 劫持：MUSA 活且无 CUDA alias 时跑 torch.musa warmup |
| vision.py / musa fa3 backend import `flash_attn_interface`（runtime 无）| raising stub 满足 import 面（真调用才 raise）|
| 默认 attention backend=fa3 需真 MUSA flash-attn wheel | 默认降级 torch_native（SDPA），同 cambricon；显式 `--attention-backend fa3` 仍可用 |

**对比为何 cambricon/enflame 不需这些**：torch_mlu 的 gpu_migration 层让
`torch.cuda.is_available()`=True（device 变 "cuda"）、torch_gcu CUDA alias 自动
激活且 PlatformFL 强制 device="gcu"（不在 ("cuda","musa") 元组跳过
init_cublas）；torch_musa 两者皆无，故 device="musa" 撞上假设 CUDA alias 的
代码。统一框架方向 = mthreads 对齐 gcu/mlu 行为（跳过 CUDA-only 路径），非
给 mthreads 造 CUDA facade（torch_musa 无 migration 层可借）。

## 3. E2E 验证（F/T 双路径 + app 镜像）

判据：HTTP 200 + completion_tokens>0 + sampling_backend=pytorch，3×
chat/completions（Qwen3-4B，`sampling_backend` 经 /server_info 确认）。

| 路径 | 编译器 | 结果 |
|---|---|---|
| F | flagtree 3.6.0 | ✅ 3/3 全过（completion_tokens=64 each）|
| T | vendor triton 3.6.0 | ✅ 3/3 全过 |
| app 镜像 | runtime 默认 flagtree | ✅ 3/3 全过（ready ~90s，ct=144）|

app 镜像：`flagos-app/sglang0.5.18-mthreads-musa5.2.0:2.1.2-0.1.dev1_g607b9672c`
（PR #749 记录）。冷启动 ~90s（workflow 默认参数即过，无需额外 knob）。

> 手动 F/T 双路径验证冷启动需 `--watchdog-timeout 900` + `SGLANG_WARMUP_TIMEOUT
> =1800`（权重加载慢、首次 kernel 编译）——workflow 单编译器路径实测 ~90s 即
> ready，未触发默认限制。

## 4. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | torchada 缺失/不 alias CUDA 的 MUSA 栈 | is_musa 接受 torch_musa（#92）|
| 2 | init_cublas 硬编码 cuda | 劫持路由 torch.musa（#92）|
| 3 | 无 flash_attn_interface | raising stub（#92）|
| 4 | fa3 backend 需真 flash-attn | 默认 torch_native（#92）|
| 5 | 无 torchvision → sglang 安装顶 torch | runtime 补 +cpu torchvision（#731）|
| 6 | 缺 compressed_tensors | deps_app pin CT（#747）|
| 7 | 裸容器拉通用 triton 3.8.0 | runtime PYTHONPATH 侧目录 shadow（无实际影响）|

## 5. 遗留

- MUSA fa3 路径未验证（需 Moore Threads 真 flash_attn_interface wheel），当前
  走 torch_native/SDPA——性能慢（decode ~2-3 tok/s eager），未优化。
- 权重加载受节点文件系统 I/O 拖慢（~10min/3 shard），非插件问题。
- 验证容器已清，节点净。
