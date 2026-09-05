# sglang 0.5.18 打包 — 端到端验证报告

> **原则：构建全部在目标机 `-build` 容器内进行，本地（macOS）不构建 wheel。**
> 每个后端在自己的 runtime `-build` 镜像
> （`flagos-runtime-<vendor>-<backend>:<version>-build`）内从同一个源包构建
> wheel；ascend aarch64 亦由 aarch64 `-build` 镜像容器内编译天然产出 aarch64
> wheel。

## 0. 背景

sglang 原生 wheel 分 CUDA / 非 CUDA 两条线。CUDA variant（`pyproject.toml`）
声明 `torch==2.13.0` 与 sglang-kernel 依赖——直接装进 FlagOS runtime 会覆盖
各后端精心匹配、反复验证过的 torch/triton 版本矩阵，并强制拉入 per-平台 ABI
的 sgl-kernel。因此需要预处理（repack）：去掉破坏环境的依赖声明，repack 后的
wheel 上传到 resource.flagos.net 的 per-vendor PyPI，供单步安装使用。

本线采用**非 CUDA variant（srt_empty 基座）**：`pyproject_other.toml` 的
`dependencies` 仅 6 项，无 torch、无 sglang-kernel；`runtime_base`（40 项，
含 transformers / llguidance / xgrammar 等纯运行时依赖）经
`merge-runtime-base.py` 合并进 `dependencies`，wheel 的 METADATA **天然零
torch、零 sglang-kernel**（repack 无需剥依赖），且 `pip install
sglang==0.5.18+flagos` 一步带齐完整运行时闭包。硬件算子全部由 runtime 内置
flag_gems + 零 sgl-kernel 路线提供（见 [playbook.md](playbook.md) §4）。

> **术语：`+flagos`** —— repack 后为 wheel 版本号追加的 PEP 440 本地版本后缀
> （`0.5.18` → `0.5.18+flagos`）。它是"这个 wheel 出自 FlagOS repack 流程"的
> 显式标记，也是单步安装能稳定命中我们的包的关键
> （见 [playbook.md](playbook.md)、[decisions.md](decisions.md) §5.1）。

---

## 文档结构

本目录按职责拆分验证报告，对齐 vllm 线 per-version 布局。四类内容各自归位：

| 类别 | 文件 | 内容 |
|---|---|---|
| 架构设计取舍与依据 | [`decisions.md`](decisions.md) | 自动化边界、风险与痛点、ADR |
| 一般性制品流转过程 | [`playbook.md`](playbook.md) | 标准流程（同一 sdist + 容器内构建 + `+flagos` + 单步安装 + 零 sgl-kernel）|
| 平台验证记录 | `backends/` | 具体平台从零到 E2E 全过的实证记录（仅参考价值信息）|
| 交付制品 | `packaging/sglang/` 根目录 + `.github/workflows/` | 脚本 / workflow / shim 源码（工具链清单见 [playbook.md](playbook.md) §7）|

后端记录按 playbook 模板组织：**环境 → 构建 → 安装 → E2E → 坑清单 → 遗留**。

### 后端索引

| 后端 | 文件 | 要点 |
|---|---|---|
| MetaX maca3.8.1.3 | [metax.md](backends/metax.md) | 首个 0.5.18 后端；零 sgl-kernel F/T 双路径 E2E 全过；app 镜像已发布（`sglang0.5.18-metax-maca3.8.1.3:2.1.2-0.1.dev1_g0900c244b`）；F/T 切换注意 flag_gems ConfigCache（根因链见 [metax-0.5.12.md](backends/metax-0.5.12.md)）|
| ascend cann9.0.0 | [ascend.md](backends/ascend.md) | aarch64 cp311；零 sgl_kernel_npu（stub 树并入共享 sgl-kernel-shim wheel + 插件 torch-native 真实现）；app 镜像已发布（`sglang0.5.18-ascend-cann9.0.0:2.1.2-0.1.dev1_g2e568482e`）|
| Cambricon neuware4.7.2 | [cambricon.md](backends/cambricon.md) | T 路径冷启动 E2E 过（无 flagtree，矩阵标 —）；app 镜像烘 watchdog 900 + warmup 1800（冷启动慢，cambricon.md §3）；runtime 补 torchvision、deps_app 补 compressed-tensors；torch_mlu CUDA 迁移层三处残缺以插件 vendor 补丁修（PR #90）|
| Enflame tops1.10.6 | [enflame.md](backends/enflame.md) | F/T 双路径 + app 镜像冷启动 E2E 过（烘 SGLANG_WARMUP_TIMEOUT=3600）；vendor 层原在 0.5.18 上静默不加载（顶层 import 漂移）已修；serve 阻塞 is_integrated / fa3 断言以插件 vendor 补丁修（PR #91）|
| NVIDIA cuda13.3 | [nvidia.md](backends/nvidia.md) | **挂起**：零 flashinfer/shim 路线在真 CUDA 不成立（shim 撑不住 sgl_kernel）；跟随插件 PR #89 完整闭包路线，待其合入 |
