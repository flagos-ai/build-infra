# sglang-plugin-FL 打包成发布镜像调研

> 调研日期：2026-08-26。仓库：https://github.com/flagos-ai/sglang-plugin-FL
> （克隆于 `~/work/sglang-plugin-FL`）。对比对象：`~/work/vllm-plugin-FL`。

## 1. 结论（TL;DR）

- **plugin 层与 vllm-plugin-FL 同构**：都是 OOT plugin，`pip install` 后通过
  entry-point 被框架发现，运行时单步安装模型成立。
- **应用层与 vllm 完全不同**：sglang 没有 "一份 wheel 通吃" 的可能——每后端锁死
  一套 `sglang × sgl-kernel × torch × python` 四元组；sgl-kernel 是 ABI 绑定
  的二进制组件，FlagCX 需按后端用 `make` 源码构建；仓库现有 `docker/` 是 **CI
  测试镜像**（`flagos-dev/sglang-plugin-fl:0.2.0-{cuda,ascend}-ci`），不是发布
  产物，也没有 vllm 那样的 `build.sh` 发布流程。
- **build-infra 统一 runtime 的 torch 版本与 sglang 各后端对不上**（见 §4）：
  除 nvidia-cuda13.3（torch 2.11.0 cu130）恰好等于 sglang cuda CI 栈外，其余
  全部错配。sglang 的 kernel 层与 torch 小版本耦合深，不能像 vllm 那样跨版本
  复用 `+flagos` wheel。
- **若立项**，正确形态是 vllm-plugin-FL `docker/build.sh` 的每后端独立镜像线，
  不是 build-infra "runtime + 单步安装" 模式——唯一例外 nvidia-cuda13.3：
  参考环境 python/torch/triton 精确一致，该后端 "runtime + 单步安装" 可能成立
  （§5.2）。每个后端都要先解决版本矩阵错配与 sgl-kernel/FlagCX 的交付方式
  （§4.3、§6.2）。是否立项是策略决策，本文只给事实与选项。

## 2. 仓库结构

```
sglang-plugin-FL/
├── pyproject.toml
├── sglang_fl/
│   ├── platform.py
│   ├── distributed/
│   │   ├── communicator.py
│   │   └── device_communicators/flagcx.py
│   └── dispatch/
│       ├── registry.py / manager.py / ops.py / policy.py
│       ├── fla_patch.py / rotary_patch.py / bridge.py
│       └── config/            # nvidia/musa/ascend/gcu/iluvatar/
│                              # kunlunxin/tsingmicro .yaml
├── docker/
│   ├── cuda/containerfile
│   ├── ascend/containerfile
│   ├── mthreads/containerfile
│   └── thead/containerfile
└── .github/workflows/_build_wheel.yml
```

- **pyproject.toml**：`version = "0.1.0"` **静态硬编码**（无 setuptools-scm），
  `dependencies = ["flag_gems", "pyyaml"]`，`packages.find` 只含 `sglang_fl*`，
  package-data 带 config yaml。entry-points：
  `[project.entry-points."sglang.srt.platforms"] sglang_fl = "sglang_fl:activate_platform"`
  与 `[project.entry-points."sglang.srt.plugins"] sglang_fl = "sglang_fl:load_plugin"`。
- **`_build_wheel.yml`**：普通 GitHub-hosted 构建（`python -m build --wheel`，
  py3.12），verify metadata 后传 artifact——**不是 audited 的 vendor-PyPI 构建**，
  与 vllm 的 `build-and-repack.sh` 流程无关。
- **`docker/`**：四个 containerfile 都是 **CI 测试镜像**，发布到
  `flagos-dev/sglang-plugin-fl:0.2.0-{cuda,ascend}-ci`，不以版本化发布镜像为目标。

## 3. 与 vllm-plugin-FL 的对比

| 维度 | vllm-plugin-FL | sglang-plugin-FL |
|---|---|---|
| 插件发现 | entry-point `vllm.plugin` / config | entry-point `sglang.srt.platforms` + `sglang.srt.plugins` |
| 版本机制 | setuptools-scm `only-version` + `_version.py`（动态） | 静态 `0.1.0` |
| docker/ 身份 | 发布流程：`build.sh` 全参数化（per-backend BASE_IMAGE/版本）+ release stage | **仅 CI 测试镜像**（`0.2.0-{cuda,ascend}-ci`） |
| 性能件 | FlagGems + FlagCX + DeepGEMM（源码构建） | FlagGems + **sgl-kernel**（ABI 绑定二进制）+ FlagCX（`make USE_*=1`） |
| wheel 通用性 | empty vllm 顶层 `py3-none-any`，一份跨后端（§5.2 ADR） | **无通用性**：sglang + sgl-kernel 每后端一个二进制栈 |
| audited 构建 | `build-and-repack.sh` → 各 vendor PyPI | 无；CI 只 `python -m build` |
| 支持后端 | 9+（nvidia/metax/ascend/musa/enflame/hygon/…） | CI 镜像 4 个：cuda/ascend/mthreads/thead |

**差异根因**：vllm 的 empty wheel 是纯 Python（硬件算子由 flag_gems/Triton
提供），所以一份 wheel + 单步安装成立；sglang 的核心性能件 **sgl-kernel**
是各后端独立编译的二进制扩展（`sglang-kernel` / `sgl-kernel-npu` /
vendor torch 配套），**随 torch 小版本变，也随后端变**——这决定了 sglang
必须走每后端镜像线。

## 4. 各后端版本矩阵（CI 镜像 vs build-infra runtime）

### 4.1 sglang-plugin-FL CI 镜像栈

| 后端 | 基础镜像 | python | torch | sglang | sgl-kernel | 备注 |
|---|---|---|---|---|---|---|
| cuda | `flagos-dev/cache:cuda-12.8.1-devel-ubuntu24.04` | 3.12 | 2.11.0 cu130 | 0.5.11 | `sglang-kernel==0.4.2` | flashinfer；FlagGems v5.3.1 源码构建；FlagCX v0.13.0 `make USE_NVIDIA=1` |
| ascend | `lmsysorg/sglang:v0.5.11-cann8.5.0-a3` | 3.11 | 2.8.0 | 0.5.11 | `sgl-kernel-npu==2026.5.1` | triton-ascend 3.2.1 替换 3.2.0；patch 6 处 stale `tl.insert_slice(` → `al.insert_slice(`；FlagGems v5.3.0；FlagCX `USE_ASCEND=1`；NPU driver 不烘焙（DooD bind-mount） |
| mthreads | `registry.mthreads.com/mcconline/inference/vllm` | 3.10 | 2.7.1 | **0.5.12** | vendor torch 配套 | **0.5.16 有 circular-import regression**（collection 即 abort），故锁 0.5.12；FlagGems v5.3.1 native `_mthreads`；FlagCX `USE_MUSA=1` |
| thead | T-Head PPU release 镜像（digest-pinned） | 3.12.3 | 2.10.0 | 0.5.12+v0.1.0.ppu2.1.0 | vendor | base 里 stale `sglang_fl 0.1.0` 被 uninstall |

### 4.2 build-infra runtime 栈（configs.yaml）

| 后端 | python | torch |
|---|---|---|
| nvidia-cuda12.8 | 3.12 | 2.10.0+cu128 |
| nvidia-cuda13.3 | 3.12 | 2.11.0+cu130 |
| ascend-cann8.5.0 | 3.11 | 2.9.0+cpu |
| ascend-cann9.0.0 | 3.11 | 2.10.0+cpu |
| mthreads-musa4.3.6 | 3.10 | 2.9.0+musa4.3.6 |
| mthreads-musa5.2.0 | 3.10 | 2.9.1+musa5.2.0 |
| metax-maca3.7.2.1 | 3.12 | 2.8.0+metax3.7.2.0 |
| metax-maca3.8.1.3 | 3.12 | 2.10.0+metax3.8.1.0 |
| hygon-dtk26.04 | 3.10 | 2.9.0+das.opt1.dtk2604 |

### 4.3 错配判定

| sglang 后端 | CI torch | runtime 对应后端 | runtime torch | 匹配? |
|---|---|---|---|---|
| cuda | 2.11.0 cu130 | nvidia-cuda13.3 | 2.11.0 cu130 | ✅ 唯一匹配 |
| cuda | 2.11.0 cu130 | nvidia-cuda12.8 | 2.10.0 cu128 | ❌ |
| ascend | 2.8.0 | ascend-cann8.5.0 | 2.9.0 | ❌ |
| ascend | 2.8.0 | ascend-cann9.0.0 | 2.10.0 | ❌ |
| mthreads | 2.7.1 | mthreads-musa4.3.6 | 2.9.0 | ❌ |
| mthreads | 2.7.1 | mthreads-musa5.2.0 | 2.9.1 | ❌ |

sglang CI 里没有 metax/hygon 镜像；build-infra runtime 没有 thead/spacemit 之外
的 PPU 后端。**除 nvidia-cuda13.3 外全部错配**——不能复用 build-infra 统一
runtime 作为 sglang 发布镜像的 base（至少 torch 层必须换）。

## 5. 插件架构与验证要点（2026-08-27 补充）

下列为打包/验证视角的事实提炼；验证工作以此为据，不需再读其他文档。

### 5.1 三层替换机制（插件架构）

插件在 SGLang 之上实现三层无侵入替换，全程不修改 SGLang 源码：

| 层 | 替换对象 | 拦截机制 | 替换内容 |
|---|---|---|---|
| Layer 1 | PyTorch ATen 算子（300+） | `torch.library.impl` → ATen dispatch table | FlagGems Triton kernel（`flag_gems.enable()`） |
| Layer 2 | SGLang fused kernel（SiluAndMul/RMSNorm/TopK/FusedMoE/RotaryEmb） | HookRegistry **AROUND** hook 拦截 `MultiPlatformOp.dispatch_forward()` | OpManager 按 flagos(150) > vendor(100) > reference(50) 路由，失败自动 fallback |
| Layer 3 | 分布式通信（GroupCoordinator 12 个方法） | HookRegistry **AROUND** hook | CommunicatorFL → FlagCX / torch.distributed（NCCL/HCCL/MCCL/CNCL） |

与打包相关的关键特性：
- **Layer 2 hook 只在模型构造时生效一次**，结果缓存为函数指针，运行时零 dispatch
  开销——与 vllm CustomOp 的 `_forward_method` 缓存同构。
- **Layer 3 有 PyNccl 抑制**：FlagCX 激活时 disable `pynccl_comm`，避免双通信库冲突。
- **FLA 算子不走 hook**（模块级函数，非 MultiPlatformOp 子类），用 monkey-patch
  替换源模块引用，且须同时 patch 调用者模块（`from X import Y` 引用绑定问题）。
- **FlagCX 按后端源码构建**：`make USE_NVIDIA=1` / `USE_ASCEND=1` / `USE_MUSA=1`，
  `FLAGCX_PATH` 指向 build 产物；`flagcxGroupStart/GroupEnd` v0.13+ 需传 comm 参数。
- **通信 backend 选择链**：`SGLANG_FL_DIST_BACKEND`(env) > `FLAGCX_PATH`(存在则
  flagcx) > `_DIST_BACKEND_MAP[vendor]`（nvidia/iluvatar/metax/thead→nccl，
  ascend→hccl，cambricon→cncl，mthreads→mccl）。
- **stream 适配三平台**：`_get_raw_stream_handle()` 只支持 cuda/npu/musa 三分支，
  新平台需加 elif 分支（打包验证时若新增平台要改 `flagcx.py`）。

### 5.2 参考环境 vs build-infra runtime

| 组件 | 参考环境 | build-infra runtime (cuda13.3) | 匹配 |
|---|---|---|---|
| Python | 3.12 | 3.12 | ✅ |
| PyTorch | 2.11.0+cu130 | 2.11.0+cu130 | ✅ |
| Triton | 3.6.0 | `triton==3.6.0` / flagtree 0.6.1 | ✅ |
| CUDA | 13.0 | 13.3 SDK | ✅ |
| SGLang | 0.5.11 | 无 | 需装 |
| sglang-kernel | 0.4.2 | 无 | 需装 |
| flashinfer | 0.6.8.post1 | 无 | 需装 |
| FlagGems | 4.2.1rc0 | 5.3.5 | ❌ 见 §5.3 |

**修正 §4.3 结论**：cuda13.3 的 python/torch/triton 三项与参考环境精确一致，缺的
只是 sglang + sgl-kernel + flashinfer 三个包（均有可安装配方）→ cuda13.3 上
"runtime + 单步安装" 模式**可能成立**，是唯一可能复用 build-infra runtime 的后
端。其余后端（ascend 2.8 / mthreads 2.7.1 …）参考环境未覆盖，维持 §4.3 原判。

### 5.3 FlagGems 版本漂移（打包前必须确认）

参考环境 FlagGems 是 **4.2.1rc0**，插件 pyproject 依赖是不带版本的 `flag_gems`。
三个事实源版本不一致：

| 来源 | FlagGems 版本 |
|---|---|
| 参考环境 | 4.2.1rc0 |
| CI docker（§4.1） | v5.3.1（源码构建） |
| build-infra runtime（configs.yaml） | 5.3.5 |

插件实际对哪个版本保证过兼容，是打包/验证前须向开发团队确认的问题（见 §7.7）。

### 5.4 验证配方（可直接用于 E2E smoke）

以下是验证所需操作事实：

- **已验证模型**：Qwen2.5-0.5B-Instruct（tp=1）、
  Qwen2.5-14B-Instruct（tp=8）、Qwen3.6-27B / Qwen3.6-35B-A3B（tp=1）——E2E
  smoke 目标模型。
- **必带启动参数**：`--disable-piecewise-cuda-graph`（FlagGems Triton kernel 含
  logging.Logger 调用，与 torch.compile / piecewise CUDA graph 不兼容；常规 CUDA
  graph 不受影响）。
- **每平台启动差异**：

| 平台 | 设备选择变量 | 特殊环境变量 | 特殊 server 参数 |
|---|---|---|---|
| CUDA | CUDA_VISIBLE_DEVICES | — | — |
| MUSA | MUSA_VISIBLE_DEVICES | MCCL_IB_DISABLE=1 | --page-size 1 |
| Ascend | ASCEND_RT_VISIBLE_DEVICES | SGLANG_ENABLE_OVERLAP_PLAN_STREAM=0, HCCL_BUFFSIZE=2400 | --attention-backend ascend --device npu --dtype bfloat16 --disable-radix-cache |

- **调试二分法**（精度二分法，与 build-infra 逐层隔离纪律同构）：
  `SGLANG_PLUGINS="__none__"`（全禁）→ `USE_FLAGGEMS=0`（只留 Layer 2）→
  `SGLANG_FL_PER_OP="silu_and_mul=flagos;rms_norm=reference"`（单算子隔离）→
  `SGLANG_FL_OOT_ENABLED=0`（只留 Layer 1）→ `SGLANG_FL_FLAGOS_WHITELIST=...`
  （逐步启用 ATen 算子）。
- **关键环境变量**：`SGLANG_FL_PREFER`（flagos/vendor/reference）、
  `SGLANG_FL_STRICT`（0=禁 fallback）、`SGLANG_FL_PER_OP`、`SGLANG_FL_OOT_WHITELIST`
  /`SGLANG_FL_OOT_BLACKLIST`、`SGLANG_FL_DENY_VENDORS`/`SGLANG_FL_ALLOW_VENDORS`、
  `SGLANG_FL_DISPATCH_LOG`、`SGLANG_FL_DIST_BACKEND`、`SGLANG_PLUGINS`
  （`__none__` 禁全部）。

## 6. 打包模型分析

### 6.1 可复用的部分（与 vllm 同构）

- **plugin wheel**：`sglang_fl` 是纯 Python，可打 `py3-none-any` wheel，经
  entry-point 被 sglang 发现。单步 `pip install sglang-fl==X+flagos` 模型
  在 **wheel 层**成立。
- **per-backend 交付**：沿 vllm-plugin-FL `docker/build.sh` 模式，为每个后端
  参数化 BASE_IMAGE + 版本变量，产出 `flagos-app/sglang-{backend}:{version}`。

### 6.2 无法复用、必须新做/决策的部分

| 组件 | 问题 | 选项 |
|---|---|---|
| 版本机制 | 静态 `0.1.0`，无 scm；CI 镜像 tag 是 `0.2.0-{cuda,ascend}-ci`（独立于 pyproject） | 引入 setuptools-scm 或改手动 bump；确定「plugin 版本」与「镜像版本」的关系 |
| sgl-kernel | ABI 绑定二进制，随 (后端, python, torch) 变 | (a) `+flagos` repack 上传各 vendor PyPI；(b) 发布镜像内现装官方版本；(c) vendor 源码构建 |
| FlagCX | 各后端 `make USE_*=1` 源码构建 | 照搬 vllm 镜像内构建；确认 sglang 的 flagcx.py 与 FlagCX 版本匹配 |
| audited 构建 | 现 CI 只 `python -m build`，非 vendor-PyPI | 参考 vllm `build-and-repack.sh`，建立 per-vendor 索引 + twine |
| 版本漂移 | sglang 每后端锁不同 sglang/sgl-kernel/torch | 每次 bump 都要逐后端对齐，无单一版本 |

### 6.3 明确的 blocker

- **torch 错配**：§4.3。sglang 的 kernel 层（sgl-kernel-npu 2026.5.1、vendor
  torch 配套 sgl-kernel、sglang-kernel 0.4.2）与 torch 小版本强耦合，跨版本装
  必崩。要么给每个后端单独做 sglang 专用 runtime（新 base 线），要么把
  build-infra runtime 的 torch 升到 sglang 栈并承担回归风险。
- **ascend NPU driver 不烘焙**：CI 镜像依赖 DooD bind-mount driver；发布镜像
  若走同构，需要确定 driver 交付方式（build-infra ascend runtime 的现有做法）。
- **mthreads sglang 版本钉死 0.5.12**：上游 0.5.16 有 circular-import
  regression，bump 受上游修复节奏限制。

## 7. 待决策

1. **是否立项**：sglang 发布镜像是一条新线（独立 base + 每后端构建 + 验证面
   翻倍），与 vllm/megatron 的 build-infra 模式不共享。
2. **发布形态**：每后端独立镜像（build.sh 模式）确认？还是先做 cuda/ascend
   两条线试点？
3. **sgl-kernel 交付**：repack 进 vendor PyPI vs 镜像内现装 vs vendor 源码构建。
4. **FlagCX 构建**：镜像内 `make` 构建是否可接受（vllm 已这么做）。
5. **torch 对齐策略**：为 sglang 建独立 runtime 线，还是等 sglang 升到
   build-infra 的 torch 版本（目前只有 nvidia-cuda13.3 对齐）。
6. **版本机制**：plugin 静态版本 → 动态/手动 bump 方案。
7. **FlagGems 版本确认**（§5.3）：参考环境 4.2.1rc0 / CI docker v5.3.1 /
   runtime 5.3.5 三源不一致，插件实际对哪个版本保证过兼容，须向开发团队确认。

## 8. 信息来源

- `~/work/sglang-plugin-FL/`：pyproject.toml、`docker/{cuda,ascend,mthreads,thead}/containerfile`、
  `.github/workflows/_build_wheel.yml`、`sglang_fl/` 包结构。
- `~/work/vllm-plugin-FL/docker/build.sh` + `docker/cuda/Dockerfile`（对比基准）。
- build-infra `configs.yaml`（runtime python/torch 版本）。
