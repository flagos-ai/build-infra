# sglang 打包路线论证：上游 wheel + sgl-kernel shim（零 sglang-kernel）

> 面向项目组开发人员的论证材料，回答两个问题：这条路**行不行**、**为什么
> 走这条路**。结论先行：路线已由 MetaX 平台端到端实证，是当前覆盖全量
> 非 NVIDIA 平台的 sglang 分发方式，且与 vllm 线同一条模式。
>
> 配套证据：[可行性分析](zero-sgl-kernel-feasibility-20260828.md)、
> [0.5.18 打包报告](sglang-0.5.18/index.md)、
> [MetaX 验证记录](sglang-0.5.18/backends/metax.md)。

## 1. 问题：为什么不能直接装官方 sglang

sglang 官方 wheel 分 CUDA / 非 CUDA 两条线，都不能直接进 FlagOS runtime：

1. **CUDA 变体锁死 torch 版本**。0.5.18 的 CUDA variant 声明
   `torch==2.13.0`，直接安装会覆盖各后端精心匹配、反复验证过的 torch/triton
   矩阵（runtime 实测 2.8~2.11）。
2. **CUDA 变体强制拉入 sglang-kernel**。CUDA variant 依赖 sglang-kernel——
   per-平台 ABI 硬编译件，随 (sglang × sglang-kernel × torch × python)
   四元组变化，没有 `py3-none-any` 通用 wheel。
3. **官方非 CUDA 变体（srt_empty）缺闭包**。只带 6 项基础依赖，缺
   runtime_base 的 40 项（transformers / llguidance / xgrammar 等），无任何
   硬件算子接线——装了也起不来，必须自建 sdist 合并闭包。
4. **官方不覆盖非 CUDA 厂商**。MetaX / mthreads / enflame / kunlunxin 等
   没有官方 sglang-kernel wheel；"等上游或厂商提供编译件"逐平台不现实。

## 2. 路线对比

| 路线 | 做法 | 结论 |
|---|---|---|
| A. 官方 wheel 原样装 | CUDA variant 直接 pip install | 破坏 torch 矩阵，阻塞 |
| B. 每后端镜像线 | vllm 旧式 build.sh，每后端一条镜像 | 镜像线数量随后端线性增长 |
| C. 每平台自编 sglang-kernel | 各后端编译 kernel 子集 wheel | 组合维护成本随组合数增长（见 §3.3）|
| D. **零 sglang-kernel**（选定） | 上游 wheel 去 torch 依赖 + import 面 shim + 硬件算子走 flag_gems | 本路线 |

C 路线的成本有实证：0.5.10 在 MetaX 上编译 10-op 子集 wheel，需改 csrc 源、
自写注册文件、逐 capability 调编译参数与 kernel 参数——每个新后端、每个
sglang 版本、每个 torch 版本都要重来一遍。成本随组合数量增长，不是线性增加。

## 3. 可行性：证据链

### 3.1 sglang 本体对 sglang-kernel 无硬依赖

- 0.5.18 代码库对 `sgl_kernel` 的 import 面共 178 处（82 个模块级符号 +
  29 个子模块），全部是模块加载期必须成功的 import——但**运行时符号从不
  被调用**（MetaX E2E 实证）。
- 非 CUDA 平台 attention 默认落 triton backend（flashinfer 检测恒 False）；
  12 个无条件顶层 import 全为 CUDA/NPU 专用文件，启动路径不可达。
- `MultiPlatformOp` 对未实现平台天然落 `forward_native`（torch 原生实现），
  不需要任何厂商 kernel。
- 因此只需一个纯 Python 的 import 面 shim（`sgl_kernel` 与全部子模块可
  import，符号访问返回 `_Dummy` 替身）即可让 sglang 正常启动。shim 不求
  "做得对"，只求"活得过去"。
- 上游 0.5.18 源码已含独立的非 CUDA 构建配置 `pyproject_others.toml`——
  上游自身就在把非 CUDA 平台作为正式构建路径演进，本路线顺此方向接线而非
  另起炉灶。

### 3.2 硬件算子全部由 flag_gems 提供

- 默认路径 6 个算子全走 flag_gems（silu_and_mul / rms_norm / rotary /
  topk / mrotary / gated_delta_rule）。
- flag_gems 设计上就是按厂商分发算子（`runtime/backend/` 下 15 个
  per-vendor 目录），与 sglang 的 vendor backend 一一对应——"每个厂商
  提供算子实现"，而非"每个厂商提供 sglang-kernel 编译件"。
- vendor backend 迁移面约 2/3 算子已有 flag_gems 直接对应，剩余缺口分级：

| 级别 | 缺口 | 处置 |
|---|---|---|
| A 级 · 已有物接线 | gemma_rmsnorm / causal_conv1d / swiglu_oai | 改调 flag_gems 或上游实现 |
| B 级 · 上游已有 | enflame topk_sigmoid / merge_state_v2 | 显式接线 |
| C 级 · 需自写 | kunlunxin klx_* 三类（attention extend / gated delta net / fused experts）| 移植进 flag_gems _kunlunxin |

### 3.3 E2E 实证链（逐级闭环）

| 日期 | 平台 | 版本 | 结果 |
|---|---|---|---|
| 2026-08-27 | nvidia-cuda12.8 | 0.5.10 | F/T 双路径全过 |
| 2026-08-28 | MetaX maca3.8.1.3 | 0.5.12 | F/T 双路径全过 |
| 2026-08-29 | MetaX maca3.8.1.3 | 0.5.18 | F/T 双路径全过 |

0.5.18 判据：`python -m sglang.launch_server` 起服务，HTTP 200 +
completion_tokens=144 + sampling_backend=pytorch，FlagTree / Triton 双路径
各 3/3 通过。

MetaX 端到端落地的改动可以数出来：约 7 处——1 个导入替身包、2 处 wheel 构建期补丁、
1 处插件修复、3 个启动开关。按能否平移分三类：

| 类别 | MetaX 实际内容 | 到其他后端 |
|---|---|---|
| 全后端共用，一次建成 | 导入替身（随 sglang 版本生成）、统一构建/repack 管线、依赖审计门禁 | 直接复用，不按后端重做 |
| 逐端实测确认，微调即可 | 3 个启动开关、3 处 JIT 缺口补丁 | 每端核对是否触发；触发则照修，不触发则略过 |
| 实测发现才修 | 算子库覆盖缺口：MetaX 为 0 | 已按 A/B/C 分级；多数端只需接线 |

**工作量怎么估。** 约一半内容（导入替身、构建管线、审计门禁）全后端共用，只随 sglang
版本重生成；另一半是"确认是否触发"的核对项，每个新后端的成本是核对与微调，按"处"计
而不是按开发量计。已知需要算子移植的只有个别厂商：enflame 2 个、kunlunxin 一类专用
算子，MetaX 本身为 0。

### 3.4 修复都落进了交付形态

MetaX 平台的三处 JIT 缺口 fallback（clamp_position / vision.py cudnn
guard / PlatformFL 签名）全部以构建期 patch 形式落进 wheel 与插件层，
不是只活在验证容器里——干净 runtime 单步安装即可复现。

### 3.5 可复现

- 同一 sdist 全后端共用（`build-sdist.sh`），每后端在各自 runtime
  `-build` 镜像容器内构建 wheel；
- `+flagos` PEP 440 后缀显式标记制品来源，`pip install sglang==0.5.18+flagos`
  稳定命中我们的包；
- 禁入依赖有审计门禁（wheel 不得携带 torch / triton / sglang-kernel 等，
  `audit-deps.py`）。

## 4. 必要性：为什么走这条路

1. **官方覆盖不了全量平台**。FlagOS 目标是 13+ 厂商；非 CUDA 平台的
   sglang-kernel 官方 wheel 不存在，路线不能建立在"等厂商提供编译件"上。
2. **kernel 层收敛到单一依赖**。flag_gems 已内置在 runtime、已按厂商分发；
   零 sglang-kernel 后，sglang 的硬件算子与 vllm / megatron 共用同一份
   flag_gems，全栈只有一份 kernel 依赖。
3. **与 vllm 线同一模式**。vllm 已全线统一 empty 模式（wheel 不含硬件
   kernel，硬件算子由插件 + flag_gems 提供，`+flagos` 单步安装）。sglang
   走同一模式，团队只需维护一套打包心智模型；一条 runtime 镜像同时服务
   megatron / vllm / sglang，镜像线不再随应用增长。
4. **架构不排他，未来可换**。shim 只占 import 面；某平台日后有了真 kernel，
   替换 wheel 即可，打包模型与安装命令不变——不为性能设上限。

## 5. 已知风险与处置

| 问题 | 现状 | 处置 |
|---|---|---|
| 性能：~4 tok/s（0.5.18）vs 基线 ~40（0.5.10 自编 kernel 子集）| 慢，未优化；跨版本不完全可比 | 正确性优先；差距属调优问题，可后续优化；性能验收口径待定 |
| 覆盖缺口：enflame 2 op、kunlunxin klx_* | 迁移面分析基线 0.5.10 | A/B 级接线、C 级移植进 flag_gems；逐后端验证 gate |
| 验证广度：目前仅 MetaX 闭环 | 其余后端未验 | verify matrix 逐后端 F/T 双路径 gate（与 vllm 线同机制）|
| 0.5.16+ circular-import 回归 | MetaX 实证未触发 | 其余后端 smoke 时覆盖 |
| 维护负担：shim 随版本更新、厂商 patch 散落 | shim 由 generate.py 生成；patch 由构建期脚本落进 wheel | 升级 sglang 版本时重跑生成 + 构建流程即可，无手工步骤 |

## 6. 待团队拍板

1. 迁移工作是否立项、优先级（hygon / enflame 先行？）
2. 缺口 op 的维护归属（flag_gems 上游 vs 我们的 patch）
3. 性能验收口径（逐后端 F/T 双路径 E2E + 吞吐对比）
