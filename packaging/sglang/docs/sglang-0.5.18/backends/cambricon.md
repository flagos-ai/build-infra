# sglang 0.5.18 — Cambricon neuware4.7.2 / neuware4.4.3 验证记录

> **验证通过（T 路径，冷启动）**。cambricon runtime 无 flagtree 编译器
> （configs.yaml `flagtree` 为空），F 路径不存在（矩阵标 —），仅 T
> （vendor triton）单路径。serve 阻塞链（torch_mlu 的 CUDA 迁移层三处残缺）
> 以插件层 vendor 补丁修复（sglang-plugin-FL PR #90）。app 镜像冷启动 E2E
> 全过（2026-09-05），但冷启动极慢——须烘 watchdog/warmup 预算（§3）。

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

## 3. E2E 验证（T 路径，2026-09-05 冷启动复核）

判据：HTTP 200 + completion_tokens>0 + sampling_backend=pytorch，3×
chat/completions（Qwen3-4B）。

| 路径 | 编译器 | 结果 |
|---|---|---|
| T | vendor triton 3.4.0+mlu | ✅ app 镜像 3/3（completion_tokens=144 each）|

> **冷启动修正**（此前「首次调优 6-7 分钟」为 warm-cache 运行，冷启动不可
> 复现，作废）：全新容器冷启动 flag_gems/triton 编译风暴下，sglang 默认
> watchdog 300s 会在 ~15min 冷调优途中杀 scheduler——须
> `--watchdog-timeout 900` + `SGLANG_WARMUP_TIMEOUT=1800`，~870s 才 ready；
> 首个请求冷调优可达 ~27min；decode ~1.1 tok/s（SDPA 走 math 后端，未优化，
> 见 §6）。app 镜像冷启动 E2E 全过（3×200/ct=144 复核）——真过但慢。这组
> 容忍值已烘进 app 镜像（§4），`docker run <app 镜像> sglang-serve ...`
> 冷启动即生效。

## 4. 运行时与代码改动

| 层 | 改动 | 落点 |
|---|---|---|
| runtime deps | 补 `torchaudio==2.11.0+cpu` + `torchvision==0.26.0+cpu` | configs.yaml（PR #723）|
| deps_app | 补 `compressed-tensors==0.17.0+flagos` | configs.yaml（PR #725）|
| app env | 冷启动预算烘进 app 镜像（watchdog 900 / warmup 1800，#738 实测）| configs.yaml env.app.sglang |
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
| 9 | 冷启动（空 ConfigCache）默认 watchdog 300s 杀 serve | app env 烘 watchdog 900 + warmup 1800（§3）|

## 6. 遗留

- 性能未优化：冷启动 decode ~1.1 tok/s（SDPA 走 torch_mlu math 后端，§3）；
  若不可接受，后续让 torch_mlu fused SDPA 真正 engage。
- 节点仅 Qwen3-4B（无 0.6B）——验证模型与 metax/ascend 的 0.6B 不同。
- 验证容器已拆，节点净。

## 7. neuware4.4.3（同 PR #90 增补头 0b9d98a78）

与 neuware4.7.2 同 PR #90，但插件分支头推进（31528294e → 0b9d98a78）：4.4.3 的
torch_mlu 1.29.2 只暴露部分 CUDA 迁移 facade，sglang 库存路径在 vendor 补丁可跑
前就断——为该后端增补三样（facade shim / flag_gems 黑名单 15→223 / SDPA GQA
视图替换），对 4.7.2 均无行为影响（4.7.2 复核见下）。工具链差异：

| 项 | neuware4.4.3 | neuware4.7.2 |
|---|---|---|
| SDK | cntoolkit 4.4.3（cnmon 6.2.15 / cncl 1.29.4 / cnnl 2.1.829）| cntoolkit 4.7.2（cnmon 6.5.48 / cncl 1.30.8 / cnnl 2.2.14）|
| Python | 3.10 | 3.12 |
| torch / torch-mlu | 2.7.1+cpu / 1.29.2+torch2.7.1 | 2.11.0+cpu / 1.33.1+torch2.11.0 |
| torchvision / torchaudio | 0.22.1+cpu / 2.7.1+cpu | 0.26.0+cpu / 2.11.0+cpu |
| vendor triton | 3.2.0+mlu1.7.2（T 路径）| 3.4.0+mlu2.1.1（T 路径）|
| flagtree | 无 | 无 |
| flag_gems | 5.3.5 | 5.3.5 |
| deps_app sglang0.5.18 | compressed-tensors==0.17.0+flagos | compressed-tensors==0.17.0+flagos |

三样增补的根因与修法（全落在 4.4.3 生效，4.7.2 不受影响）：

1. **activation 期 facade shim**（`vendor/cambricon/shim.py`，activate_platform
   最早 per-process 钩子 + load_plugin 兜底）：torch_mlu 1.29.2 缺
   `torch.cuda.memory` mempool 符号——pynccl_allocator import
   `_cuda_beginAllocateCurrentThreadToPool` / `_cuda_endAllocateToPool` 在
   sglang import 即 ImportError；且 `torch.Stream` 是包装器非类，
   breakable_cuda_graph 的 isinstance 检查失败。
2. **flag_gems 黑名单 15 → 223 个已注册 impl fn**（config/cambricon.yaml 头部
   注释记收敛过程）：4.4.3 的 triton 3.2.0+mlu1.7.2 与 4.7.2 的 3.4.0+mlu 不同
   代——原 15 个 pointwise 的 in-place/tensor 兄弟、compare、bitwise、
   index/masked 写与 sampling 链复合族同属一个编译失败类，真实 decode 流量下逐
   一暴露。两个下划线 impl（`_index_put_impl_` / `_unsafe_masked_index_put_accumulate`
   ）在 decode 规模把 grid 排到 batch*vocab，超 MLU 65535 grid 上限崩 serve
   （sampler.py:583 top-k masked setitem；4x16 probe 是小规模假绿），family 前缀
   扫不到下划线名，须逐名列出。
3. **SDPA GQA 兜底换纯视图展开**：repeat_interleave 走 flag_gems，随 KV 增长每
   decode 步重编译形状特化 triton kernel——0.04 tok/s 且 watchdog 中途杀
   scheduler。改 unsqueeze/expand/reshape + 一次 contiguous copy（形状无关，
   torch.equal 实证与 repeat_interleave 逐字节一致），decode 平坦 ~1.2 tok/s。

验证记录（app 镜像 `flagos-app/sglang0.5.18-cambricon-neuware4.4.3:2.1.2-0.1.dev1_g0b9d98a78`，
push digest sha256:15f7aec83d32c2dc7e33954096b2a2c579520e72a653b472fba95687f45adbb8）：

- 重建 app 镜像上 serve gate 4× chat/completions 全过（ct=60、temp 0.3/0.0、
  sampling_backend=pytorch），中文请求/响应无乱码（cjk_ratio 0.82/0.75、
  mojibake=[]）。
- 4.7.2 无回归复核（改后插件头 0b9d98a78）：3/3 过（ct=144、
  sampling_backend=pytorch）——triton 3.4.0+mlu 编译这 223 个 kernel 均无问
  题，排除项在其上无行为差异（同类 4x16 probe 与 serve 规模一致）。
- deps_app 同 4.7.2 pin compressed-tensors==0.17.0+flagos（sglang serve 无条件
  import quantization 链，同根因 §4 #725）。

遗留同 neuware4.7.2（§6）：decode ~1.1-1.2 tok/s（SDPA math 后端未优化）、
节点仅 Qwen3-4B（无 0.6B，verify 需 `--model` 覆盖）。
