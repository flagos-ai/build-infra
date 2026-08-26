# vllm 0.24.0 — nvidia cuda12.8 / cuda13.3

> 本文对应原报告 §6。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 6. NVIDIA（CUDA 12.8 / 13.3）详细记录

日期：2026-08-16
节点：`h20`（H20 GPU，x86_64）
镜像：`flagos-runtime-nvidia-cuda12.8:2.1.2` / `flagos-runtime-nvidia-cuda13.3:2.1.2`
模型：Qwen3-4B（`/models/Qwen3-4B`，由 `/data/tqm/models` 挂载）
参数：`--enforce-eager --dtype bfloat16`，端口 8031/8032

### 6.0 插件基线：v0.3.0-dev

NVIDIA 路径使用 vllm-plugin-FL 的 **`v0.3.0-dev` 分支**（官方 0.24.0 适配线，
tar.gz 解包到 `/app/vllm-plugin-FL`；与 main 分支的差异与合并路线见
[§7](../decisions.md)），在 dev 分支上 **无需任何 monkey-patch**。

### 6.1 关键阻塞点与解决

1. **CUDA 平台无条件 import flashinfer**：0.24.0 的 CUDA 平台代码在
   `flashinfer_sampler_supported()` 中检查环境变量 `VLLM_USE_FLASHINFER_SAMPLER`
   （默认 True）后就 import flashinfer。Runtime 镜像未装 flashinfer，
   启动即报 import 错误。

   解决：启动时设置 **`VLLM_USE_FLASHINFER_SAMPLER=0`**（环境变量开关，
   非代码修改）。日志确认：`FlashInfer top-p/top-k sampling disabled via
   VLLM_USE_FLASHINFER_SAMPLER=0`。

2. **插件安装必须 `--no-build-isolation`**：pip 构建隔离会独立下载
   pyproject 声明的构建依赖 —— 其中 `torch>=2.7.1` 从 pypi.org 拉取约 2.4GB，
   且会**用下载的 torch 构建插件**。这与 repack 的初衷（保护 Runtime 镜像中
   精心匹配的版本矩阵）直接冲突，绝不允许。

   解决：先盘点 Runtime 环境已有工具链（setuptools 81.0.0、pybind11 3.0.3、
   ninja 1.13.0 已具备；缺 `wheel`、`scikit-build-core==0.11`、`cmake`），
   从**厂商 PyPI 索引**（`flagos-pypi-nvidia`）补齐缺失项，再
   `pip install -e . --no-build-isolation`（约 30 秒完成）。

   长期方案：随 [§7](../decisions.md) 合并路线将插件以 **wheel 形式发布**后，
   源安装路径整体消失 —— 预编译 wheel 不需要任何构建工具链，无需把
   `wheel`/`scikit-build-core`/`cmake` 常驻进共享 Runtime 镜像（它们只为单步
   源安装临时补齐）。

### 6.2 验证结果

**CUDA 12.8（torch 2.10.0+cu128，python 3.12）**

- flagtree 3.6.0（`/opt/flagtree`，默认）：✅ 启动 + 推理通过
- triton 3.6.0（`/opt/triton`）：✅ 启动 + 推理通过
- 安装：`pip install vllm==0.24.0+flagos` 单步（`Using cached
  vllm-0.24.0%2Bflagos-cp312-cp312-linux_x86_64.whl (7.8 MB)`，无新下载）

**CUDA 13.3（torch 2.11.0+cu130，python 3.12）**

- flagtree 3.6.0：✅ 启动 + 推理通过
- triton 3.6.0：✅ 启动 + 推理通过
- 安装：插件 `--no-build-isolation` + vllm 单步

两种编译器、两个 CUDA 版本的推理输出完全一致：
`' Paris. The capital of Germany is Berlin. The capital of Italy is Rome.'`
（finish=length，模型指纹 `vllm-0.24.0-423da8ca`）。

### 6.3 跨 CUDA 版本复用（重要结论）

12.8 与 13.3 同为 python 3.12，**共用一个 cp312 empty wheel**
（`vllm-0.24.0+flagos-cp312-cp312-linux_x86_64.whl`）。13.3 验证同时回答了
"相同 cp 版本的 Wheel 是否可跨 CUDA 使用"：**12.8 构建的 wheel 直接在 13.3
（cu130）上单步安装并运行通过**。是否可跨 OS/架构（如 aarch64）仍待验证。

### 6.4 App 镜像 serve 验证（2026-08-24，wheel 单步安装）

§6.2 的空模式验证在 dev 基线上完成（源安装 v0.3.0-dev 插件）。现 v0.3.0-dev 分支已删，
改从 **main 分支取快照**（HEAD `a9435a3`，2026-08-21，即 tag v0.3.0-rc0）构建插件 wheel
`vllm_plugin_fl-0.2.0+ga9435a3.d20260821`，经 `vllm-app-image.yml` 构建 app 镜像
`flagos-app/vllm0.24.0-nvidia-cuda12.8:2.1.2-0.2.0_ga9435a3.d20260821`（wheel 单步安装
vllm `0.24.0+flagos` + 插件 wheel）并 push Harbor（记录 PR #504）。

对已 push 镜像实测 serve（`--enforce-eager --dtype bfloat16 --max-model-len 2048`，
端口 8031）：
- F 路径（默认 flagtree）：✅ `Application startup complete` + 推理连贯
- T 路径（`compiler triton`）：✅ 同上
- 输出 `' Paris. The capital of Germany is Berlin. The capital of Italy is Rome.'`，
  模型指纹 `vllm-0.24.0-60a3ac76`（不同于空模式 `423da8ca` —— 本格为 main 快照 wheel）。

注：app 镜像 CMD 默认 `--model /data/models/Qwen3-4B`，h20 上该路径不存在，
serve 实测用 `--model /data/tqm/models/Qwen3-4B` 覆盖。

---
