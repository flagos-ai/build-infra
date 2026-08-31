# vllm 0.24.0 repack — 端到端验证报告

> **原则：上游 PR 不自 merge，review 期间用 PR head 推进制品。**
> 提给上游仓库的 PR 由各自维护团队合并。
> 为保证 review 期间不阻塞，用 PR head 构建 wheel → 验证 → 打镜像（版本指向
> PR head commit）；PR 合并后重走一遍流程产出定稿制品。中间 PR-head 制品只用于
> 推进验证，不作为发布件。

> 我们把 vllm 0.24.0 重新打包成"不显式声明对 Torch/Triton 的依赖”的 Wheel 包。
> Wheel 包使用上游社区的 0.24.0 sdist 版本，使用 VLLM_TARGET_DEVICES=empty 模式编译。
> 这类 Wheel 包在安装的时候不会覆盖下层（Runtime）镜像中已经精心匹配、验证的版本矩阵。
> 新的 Wheel 包使用原来包的版本（`0.24.0`）加上 `+flagos` 以便区分，并且避免
> pip 等安装工具的时候错误选择其他 PyPI 源的同名、同版本软件包。
>
> 新的 Wheel 包在安装之后使用各 GPU/NPU 厂家所提供的运行时。
> 为确保最终生成的软件堆栈有效，需要逐个后端（Backend）地到对应的物理环境执行验证，
> 确保新的 Wheel 包及其依赖项能够正确安装、vLLM 软件栈可正常启动并执行推理任务。
> 本文记录各后端的验证过程与结果：
> - metax 见 [§3–§5](backends/metax.md)（MACA SDK 3.7.2.1 / 3.8.1.3 × 双编译器，4 环境全通过）；
> - nvidia 见 [§6](backends/nvidia.md)（CUDA 12.8 / 13.3 × 双编译器，空模式，全通过）；
> - mthreads 见 [§8–§9](backends/mthreads.md)、ascend 见 [§10](backends/ascend.md)、
>   sunrise 见 [§11](backends/sunrise.md)、hygon 见 [§12](backends/hygon.md)、
>   kunlunxin 见 [§13](backends/kunlunxin.md)、iluvatar 见
>   [§14](backends/iluvatar.md)、tsingmicro 见 [§15](backends/tsingmicro.md)。
>
> 类似的工作也在 0.20.2 版本的 vLLM 上开展，相关记录见
> [vllm-0.20.2/index.md](../vllm-0.20.2/index.md)。

---

## 文档结构

本目录按职责拆分验证报告，替代原单文件 `report-vllm-0.24.0.md`：

| 文件 | 内容 |
|---|---|
| [`playbook.md`](playbook.md) | §2 · 0.24.0 相比 0.20.2 的变化（只列影响打包的部分）+ 附录 · 验证命令 |
| [`decisions.md`](decisions.md) | §7 · 版本推进协作问题 |
| `backends/` | §4–§15 · 后端验证记录（worked examples）|

后端记录按 [§2](playbook.md) 的差异点组织：**环境 → 阻塞点 → 验证 → Stack → 待办**。完整标准流程
（empty 构建 + `+flagos` + 单步安装）见 [vllm-0.20.2/playbook.md](../vllm-0.20.2/playbook.md)。

### 后端索引

| 后端 | 文件 | 要点 |
|---|---|---|
| MetaX maca3.7.2.1 / maca3.8.1.3 | [metax.md](backends/metax.md) | §4–§5；四环境矩阵（×双编译器）全通过 |
| NVIDIA cuda12.8 / cuda13.3 | [nvidia.md](backends/nvidia.md) | §6；空模式零 patch 双编译器全通过 |
| mthreads musa5.2.0 / musa4.3.6 | [mthreads.md](backends/mthreads.md) | §8–§9 |
| ascend cann9.0.0 / cann8.5.0 | [ascend.md](backends/ascend.md) | §10；CANN 双栈双编译器 + app 镜像 |
| sunrise tangrt1.2.0 | [sunrise.md](backends/sunrise.md) | §11；cp310 + CUSTOM 移植；FlagTree 挂死已修复 |
| hygon dtk26.04 | [hygon.md](backends/hygon.md) | §12；F/T 双编译器；flagtree wheel 待建 |
| kunlunxin xre5.37.1 | [kunlunxin.md](backends/kunlunxin.md) | §13；cp310 + PR #401 + app 镜像 serve |
| iluvatar corex4.5.0 | [iluvatar.md](backends/iluvatar.md) | §14；cp312 empty wheel；F/T 双编译器 app 镜像 |
| tsingmicro tsm260610 | [tsingmicro.md](backends/tsingmicro.md) | §15；cp310；KV 写路径修复 PR #421；F/T 双编译器 |

---

## 0. 结论摘要（TL;DR）

结论：Metax 全线 4 种环境全部验证通过；NVIDIA 2 种 CUDA 环境（×双编译器）全部验证通过；
Ascend（CANN 9.0.0）验证通过（插件 PR #387 移植，2026-08-17）；Sunrise（TANGRT 1.2.0）
验证通过（cp310 wheel + 插件 CUSTOM 移植 + triton 路径，2026-08-19）；Kunlunxin
（XRE 5.37.1）验证通过（cp310 empty wheel + 插件 PR #401 移植 + app 镜像 serve，
2026-08-23，[§13](backends/kunlunxin.md)）。

- 构建 + 重新打包（wheel）：✅ 通过（2026-08-12）
- MACA（3.7.2.1）× FlagTree：✅ 通过（2026-08-14）
- MACA（3.7.2.1）× Triton：✅ 通过（2026-08-13）
- MACA（3.8.1.3）× FlagTree：✅ 通过（2026-08-15）
- MACA（3.8.1.3）× Triton：✅ 通过（2026-08-15）
- CUDA 12.8 × FlagTree：✅ 通过（2026-08-16，空模式）
- CUDA 12.8 × Triton：✅ 通过（2026-08-16，空模式）
- CUDA 13.3 × FlagTree：✅ 通过（2026-08-16，空模式）
- CUDA 13.3 × Triton：✅ 通过（2026-08-16，空模式）
- Ascend（CANN 9.0.0）× FlagTree：✅ 通过（2026-08-17，插件 PR #387，Qwen3-4B）
- Sunrise（TANGRT 1.2.0）× Triton：✅ 通过（2026-08-19，cp310 wheel +
  CUSTOM 移植，Qwen3-8B）
- Kunlunxin（XRE 5.37.1）× FlagTree：✅ 通过（2026-08-23，cp310 empty
  wheel + 插件 PR #401 + app 镜像 serve E2E，Qwen3-4B）
- Iluvatar（COREX 4.5.0）× FlagTree / Triton：✅ 通过（2026-08-30，cp312
  empty wheel + app 镜像 serve E2E，Qwen3-4B，[§14](backends/iluvatar.md)）
- Tsingmicro（TSM 260610）× FlagTree / Triton：✅ 通过（2026-08-31，cp310
  empty wheel，F/T 双路径 E2E，Qwen3-4B，[§15](backends/tsingmicro.md)）

"通过" 意味着：1） vLLM 服务可以正常启动；2）使用 Qwen3-4B 模型可以执行正常推理服务；

**跨 SDK 版本兼容性事项**

- MACA SDK 3.7.2.1 中编译器版本为 Triton 3.0.0，MACA SDK 3.8.1.3 中 Triton
  升级为 3.6.0 版本。Triton 3.0.0 不能很好地处理 vLLM 0.24.0 中使用的新版本
  Triton 语法，因此，在 MACA SDK 3.7.2.1 环境下选择 Triton 做编译器时，
  需要打补丁（链接？）。这些兼容性补丁的写法考虑了新版本 SDK 中 Triton
  已升级的情况，在新版本环境下也可正常运行。

- 所有用于适配的补丁都针对 vllm-plugin-FL 代码，不修改官方 vLLM 。

---

## 1. 背景

- vLLM 0.24.0 的构建脚本会尝试编译几个 Rust 组件。我们的构建容器没有 Rust 工具链，
  这些组件被静默跳过，产出一个"只有 Python 代码、没有任何编译产物"的 Wheel。

- Runtime 镜像里并列安装了 FlagTree 和 Triton 两个编译器，用 `compiler` 函数切换。
  与 MetaX 的两种 SDK 组合，形成 4 种环境（见 §3）。

---

## 3. 验证总览：metax 四环境矩阵

MetaX 两个后端的基础软件包和编译器版本不同，行为可能不同，要逐一验证。

- **3.7.2.1 + flagtree**：torch 2.8.0，flagtree **0.6.1+metax3.6**
  （triton 3.6.0 基座，最新版）→ ✅ 2026-08-14（[§4.3](backends/metax.md)）
- **3.7.2.1 + triton**：torch 2.8.0，triton 3.0.0+metax3.7.2.0
  → ✅ 2026-08-13（[§4.2](backends/metax.md)）
- **3.8.1.3 + flagtree**：torch 2.10.0，flagtree 0.6.1+metax3.6
  → ✅ 2026-08-15（[§5](backends/metax.md)）
- **3.8.1.3 + triton**：torch 2.10.0，triton 3.6.0+metax3.8.1.0
  → ✅ 2026-08-15（[§5](backends/metax.md)）

**被否决的配置：**

- MACA SDK 3.7.2.1 中内置了 FlagTree 3.1.0 版本的 Wheel 包，这一版本在 0.24.0 上有两个 API 缺口
  （`triton.jit` 缺 `do_not_specialize_on_alignment` 参数、缺 `knobs` 模块）。
  在验证 flagtree `0.6.1+metax3.6` 版本可用于此 SDK 版本之后，决定弃用厂商提供的
  flagtree 包，不再验证 3.1.0 版本 FlagTree。

---

## 16. 遗留事项

- [ ] `setuptools 84.0.0` 不满足 pyproject 中 `<81` 要求 —— 非致命问题，先不动，留意。
- [x] **插件 PR #386（torchvision guard）合入 v0.3.0-dev** —— 2026-08-17
      已合入（5b592be）；ascend 验证即基于该基线（[§10](backends/ascend.md)）。
- [ ] 0.24.0 其余后端（iluvatar、enflame、cambricon 等）
      的验证 —— nvidia ✅（[§6](backends/nvidia.md)）；metax ✅
      （[§4/§5](backends/metax.md)）；mthreads ✅（[§8/§9](backends/mthreads.md)）；
      ascend ✅（[§10](backends/ascend.md)，CANN 9.0.0 + cann8.5.0 双编译器）；
      sunrise ✅（[§11](backends/sunrise.md)，T 路径 triton；F 路径 rebuilt
      flagtree ✅ [§11.5](backends/sunrise.md) —— 旧
      [0.20.2 §2.9](../vllm-0.20.2/backends/sunrise.md) 解码挂死已由 PR 978
      修复）；hygon ✅（[§12](backends/hygon.md)，F/T 双编译器，2026-08-20）；
      **kunlunxin ✅（[§13](backends/kunlunxin.md)，flagtree + triton 双编译器，
      2026-08-23）**；**iluvatar ✅（[§14](backends/iluvatar.md)，cp312 empty
      wheel + F/T 双编译器 app 镜像 serve E2E，2026-08-30）**；
      **tsingmicro ✅（[§15](backends/tsingmicro.md)，KV 写路径修复
      PR #421，F/T 双路径 E2E，2026-08-31）**
- [ ] kunlunxin patch.py 三个 FLA 目标重指（`vllm.third_party.
      flash_linear_attention` → `vllm.model_executor.layers.fla.ops`）——
      Qwen3-Next/GDN 模型验证前置（[§13.4](backends/kunlunxin.md)）
- [ ] kunlunxin 否定指令型 prompt 标点循环 —— 已证与 alpha 无关（prompt
      内容特性，[§13.6](backends/kunlunxin.md)），留待 Qwen3-Next 验证时观察
- [ ] hygon flagtree hygon wheel 重建（PR #1020 合入后固化到
      `packaging/flagtree/hygon`，替换容器内临时 sed）
- [ ] hygon app 镜像 —— **暂不做**（2026-08-20 决策）：F 路径默认
      编译器被 PR #1020 合入 + `packaging/flagtree/hygon` wheel 重建
      发布卡死（无新 flagtree release 前 runtime 镜像无法刷新）；T
      路径（vendor triton 3.5.1 已在 runtime，同 [sunrise §11.6](backends/sunrise.md)
      烘焙 `compiler triton` 先例）技术上今天可做，但同轮交付意义不大。
      PR #1020 合入、wheel 重建后可重估。
- [ ] ascend flag_gems 5.3.4 `index_select.py:45` 逻辑 and/or 弃用警告
      （[§10.2](backends/ascend.md)，非致命）—— 上游 flag_gems 侧修复后复验
