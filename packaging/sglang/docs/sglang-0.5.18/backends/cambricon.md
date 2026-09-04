# sglang 0.5.18 — Cambricon neuware4.7.2 验证记录

> **2026-09-04 验证通过（T 路径）**。cambricon runtime 无 flagtree 编译器
> （configs.yaml `flagtree` 为空），F 路径不存在（矩阵标 —），仅 T
> （vendor triton）单路径。serve 阻塞链（torch_mlu 的 CUDA 迁移层三处残缺）
> 以插件层 vendor 补丁修复（sglang-plugin-FL PR #90）。

## 1. 环境

| 项 | 值 |
|---|---|
| 镜像 | `flagos-runtime-cambricon-neuware4.7.2:2.1.2`（`-build` 重建，含 torchvision fix，见 §4）|
| Python | 3.12 |
| torch | 2.11.0+cpu（torch-mlu 1.33.1+torch2.11.0，PrivateUse1）|
| vendor triton | 3.4.0+mlu2.1.1 @ `/opt/triton`（T 路径）|
| flagtree | 无（F 路径不存在）|
| flag_gems | 5.3.5 |
| sglang | 0.5.18+flagos（srt_empty 基座 wheel）|
| sgl_kernel | sgl-kernel-shim 0.5.18 |
| sglang-plugin-FL | exp/0.5.18-cambricon 分支（PR #90，单 commit）|
| numpy | 1.26.4 |
| 模型 | Qwen3-4B（节点无 Qwen3-0.6B，verify 需 `--model` 覆盖）|

## 2. 构建与安装

- 构建：`build-and-repack.sh cambricon-neuware4.7.2`，`+flagos` repack，上传
  `flagos-pypi-cambricon`。cargo 依赖走 rsproxy.cn 镜像（#721：crates.io 在该
  节点 <1KB/s 超时，rsproxy 秒达）。
- 安装（vendor index + aliyun extra）：

```bash
pip install sglang==0.5.18+flagos sgl-kernel-shim==0.5.18 \
    compressed-tensors==0.17.0+flagos scipy<1.18 \
    --index-url .../flagos-pypi-cambricon/simple/ \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple/
```

- `compressed-tensors==0.17.0+flagos` 为 serve 硬依赖（quantization 链 import
  到 CT，非 CUDA 也触发，同 metax/ascend），已入 configs.yaml
  `deps_app.sglang0.5.18`（PR #725）。

## 3. E2E 验证（T 路径，2026-09-04）

判据：HTTP 200 + completion_tokens>0 + sampling_backend=pytorch，3×
chat/completions（Qwen3-4B）。

| 路径 | 编译器 | 结果 |
|---|---|---|
| T | vendor triton 3.4.0+mlu | ✅ 3/3 全过（completion_tokens=32 each）|

> 性能极慢（~1 tok/s，首次调优 6-7 分钟）：SDPA 走了 torch_mlu 的 math
> 后端（fused SDPA 对 gathered KV 不接受 → 回退 math）。未优化，见 §6。

## 4. 运行时与代码改动

| 层 | 改动 | 落点 |
|---|---|---|
| runtime deps | 补 `torchaudio==2.11.0+cpu` + `torchvision==0.26.0+cpu` | configs.yaml（PR #723）|
| deps_app | 补 `compressed-tensors==0.17.0+flagos` | configs.yaml（PR #725）|
| 插件 | 新增 `vendor/cambricon/patch.py` 三处 torch_mlu 兜底 | sglang-plugin-FL PR #90 |
| 插件 | 新增 `config/cambricon.yaml`（flag_gems cumsum 黑名单）+ `get_platform_name()` 识别 | 同上 |

**runtime torchvision fix（#723）根因**：sglang wheel 依赖链（timm）要求
unversioned torchvision，runtime 未装 → pip 拉最新通用 torchvision 0.29.0
（pin torch 2.14.0）→ 顶掉 runtime 的 torch 2.11.0+cpu → matrix-inertness gate
拦下。补配套 `+cpu` torchvision 后安装保持惰性（torch 不再漂移）。

**插件三处兜底（#90）根因**：torch_mlu 的 CUDA 迁移层伪装成 CUDA 但不完整：

1. `_MLUDeviceProperties.is_integrated = False`（类级注入）——
   `get_available_gpu_memory` 读 `props.is_integrated`，torch_mlu 缺该字段。
   必须类级：sglang 多模块在插件加载前就 `from sglang.srt.utils import ...`
   绑定了函数，getattr guard 到不了那些调用点。
2. `get_device_capability` → (8,0)——torch_mlu 谎报 (5,0)，sglang 架构门读成
   sm50 legacy → 强制 fp16 降级 + 报 "sm75 only"。伪装 sm80 保持 dtype 并过门。
3. SDPA `enable_gqa`——sglang torch_native 后端对 GQA 模型传 `enable_gqa=True`；
   torch_mlu fused SDPA 不接受 gathered KV 形状 → 回退 math 后端，其签名早于
   `enable_gqa` kwarg（TypeError）。包一层：展开 KV 头 + 去掉 enable_gqa。

**cumsum 黑名单**：flag_gems cumsum 在 MLU 上算错（实证），需黑名单路由回
vendor/stock。放 config yaml 而非 patch.py：patch 在 load_plugin 第 5 步加载，
而 flag_gems 黑名单第 1 步就读了。

## 5. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | 无 torchvision → sglang 安装顶掉 torch | runtime 补配套 +cpu torchvision（#723）|
| 2 | serve 缺 compressed_tensors | deps_app pin CT +flagos（#725）|
| 3 | `is_integrated` 缺失杀 scheduler | 插件类级注入 False（#90）|
| 4 | 设备能力谎报 (5,0) → fp16 降级 | 插件伪装 (8,0)（#90）|
| 5 | SDPA enable_gqa TypeError | 插件 KV 展开 + 去 kwarg（#90）|
| 6 | flag_gems cumsum 算错 | config 黑名单（#90）|
| 7 | 容器内 github clone 不可达 | 节点 host clone + docker cp（见 verify 脚本缺陷）|
| 8 | crates.io 构建超时 | cargo rsproxy 镜像（#721）|

## 6. 遗留

- 性能 ~1 tok/s 未优化（SDPA 走 math 后端）；若不可接受，后续让 torch_mlu
  fused SDPA 真正 engage。
- 节点仅 Qwen3-4B（无 0.6B）——验证模型与 metax/ascend 的 0.6B 不同。
- 验证容器已拆，节点净。
