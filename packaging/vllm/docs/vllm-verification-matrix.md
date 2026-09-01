# vllm repack 验证矩阵

> 规划工具，随验证推进更新。每单元格 = 对应后端 runtime 镜像 + `vllm X.Y.Z+flagos`
> 单步安装后，serve + 推理（Qwen3-4B）跑通的验证。
> 状态结论、根因与修复细节见 [vllm-0.20.2/index.md](vllm-0.20.2/index.md) 和
> [vllm-0.24.0/index.md](vllm-0.24.0/index.md)；本矩阵只记录状态。

## 状态图例

| 符号 | 含义 |
|---|---|
| ✅ | 已验证通过（serve + 推理 E2E） |
| ❌ | 已屏蔽 / 验证失败有结论（不交付，或需回退路径） |
| ⛔ | 挂起（需先解决上游阻塞） |
| ？ | 成功概率不确定（缺 vendor 变体依赖） |
| ⬜ | 待验证 |
| — | 该后端无此编译器 |

列名后缀：T = Triton 编译器，F = FlagTree 编译器。

PR 表"状态"列在渲染时经 `gh` 实时查询 PR 合并状态（已合并 / OPEN / 已关闭）；
查询失败显示 `—`，重新渲染即刷新。

## 矩阵

<!-- status-matrix:verification -->

| 厂商 | 后端 | 0.20.2(T) | 0.20.2(F) | 0.24.0(T) | 0.24.0(F) |
|---|---|---|---|---|---|
| 英伟达 | CUDA 12.8 | ✅ | ✅ | ✅ | ✅ |
| 英伟达 | CUDA 13.3 | ✅ | ✅ | ✅ | ✅ |
| 昇腾 | CANN 8.5.0 | ✅ | ✅ | ✅ | ✅ |
| 昇腾 | CANN 9.0.0 | ✅ | ✅ | ✅ | ✅ |
| 寒武纪 | NEUWARE 4.4.3 | ✅ | — | ⬜ | — |
| 寒武纪 | NEUWARE 4.7.2 | ✅ | — | ⬜ | — |
| 燧原 | TOPS 1.9.10 | ✅ | ❌ | ⬜ | ⬜ |
| 燧原 | TOPS 1.10.6 | ✅ | ❌ | ⬜ | ⬜ |
| 海光 | DTK 26.04 | — | ✅ | ✅ | ✅ |
| 天数智芯 | COREX 4.4.0 | ⬜ | ❌ | ⬜ | ⬜ |
| 天数智芯 | COREX 4.5.0 | ✅ | ✅ | ✅ | ✅ |
| 昆仑芯 | XRE 5.37.1 | ✅ | ✅ | ✅ | ✅ |
| 沐曦 | MACA 3.7.2.1 | ✅ | ✅ | ✅ | ✅ |
| 沐曦 | MACA 3.8.1.3 | ✅ | ✅ | ✅ | ✅ |
| 摩尔线程 | MUSA 4.3.6 | ✅ | ✅ | ✅ | ✅ |
| 摩尔线程 | MUSA 5.2.0 | ✅ | ✅ | ✅ | ✅ |
| 进迭时空 | SPACEMIT | ⬜ | — | ⬜ | — |
| 曦望 | TANGRT 1.2.0 | ✅ | ✅ | ✅ | ✅ |
| 平头哥 | PPU 2.0.0 | ⬜ | — | ⬜ | — |
| 清微智能 | TSM 260610 | ⬜ | ⬜ | ✅ | ✅ |

**后端级上游 PR（验证/镜像基于 PR 分支 Head 的跟踪项）**

| 厂商 | 后端 | App | PR | 状态 |
|---|---|---|---|---|
| 昇腾 | CANN 8.5.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/361 | OPEN |
| 昇腾 | CANN 8.5.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/402 | OPEN |
| 昇腾 | CANN 8.5.0 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/387 | OPEN |
| 昇腾 | CANN 9.0.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/361 | OPEN |
| 昇腾 | CANN 9.0.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/402 | OPEN |
| 昇腾 | CANN 9.0.0 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/387 | OPEN |
| 寒武纪 | NEUWARE 4.4.3 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/411 | OPEN |
| 寒武纪 | NEUWARE 4.7.2 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/411 | OPEN |
| 寒武纪 | NEUWARE 4.7.2 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5745 | 已合并 |
| 寒武纪 | NEUWARE 4.7.2 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5510 | 已合并 |
| 燧原 | TOPS 1.9.10 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5345 | 已合并 |
| 燧原 | TOPS 1.10.6 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5345 | 已合并 |
| 海光 | DTK 26.04 | vllm0.24.0 | https://github.com/flagos-ai/FlagTree/pull/1020 | 已合并 |
| 昆仑芯 | XRE 5.37.1 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/268 | 已合并 |
| 昆仑芯 | XRE 5.37.1 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/400 | OPEN |
| 昆仑芯 | XRE 5.37.1 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/401 | OPEN |
| 摩尔线程 | MUSA 4.3.6 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/386 | 已合并 |
| 摩尔线程 | MUSA 4.3.6 | vllm0.24.0 | https://github.com/flagos-ai/FlagGems/pull/5130 | 已合并 |
| 摩尔线程 | MUSA 5.2.0 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/386 | 已合并 |
| 摩尔线程 | MUSA 5.2.0 | vllm0.24.0 | https://github.com/flagos-ai/FlagGems/pull/5130 | 已合并 |
| 曦望 | TANGRT 1.2.0 | vllm0.20.2 | https://github.com/flagos-ai/FlagTree/pull/978 | 已合并 |
| 曦望 | TANGRT 1.2.0 | vllm0.24.0 | https://github.com/flagos-ai/FlagTree/pull/978 | 已合并 |
| 清微智能 | TSM 260610 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/421 | OPEN |

<!-- /status-matrix:verification -->

## 设施落地

> 数据驱动自 `packaging/vllm/status_matrix.*.yaml`（schema 与刷新机制见
> docs/status-matrix.md）。deps_app 落库 = configs.yaml 的 deps_app key 存在
> （该 backend 可构建此 app）；镜像发布 = 该 app 镜像已推送 Harbor。

<!-- status-matrix:facility:vllm0.20.2 -->

### vllm0.20.2

> 数据截止：2026-08-29

**App 级设施（全后端共享）**

| 事项 | 状态 |
|---|---|
| Containerfile | ✅ |
| 构建 workflow | ✅ |

**后端级设施**

| 后端 | deps_app 落库 | 启动文档 | 镜像发布 | 备注 |
|---|---|---|---|---|
| CUDA 12.8 | ✅ | ✅ | ✅ | — |
| CUDA 13.3 | ✅ | ✅ | ✅ | — |
| CANN 8.5.0 | ✅ | ✅ | ✅ | — |
| CANN 9.0.0 | ✅ | ✅ | ✅ | — |
| NEUWARE 4.4.3 | ✅ | ✅ | ✅ | — |
| NEUWARE 4.7.2 | ✅ | ✅ | ✅ | — |
| TOPS 1.9.10 | ✅ | ✅ | ⬜ | app 镜像未发布：F 路径 ❌（等待 [FlagGems #5345](https://github.com/flagos-ai/FlagGems/pull/5345) 合入后重建） |
| TOPS 1.10.6 | ✅ | ✅ | ⬜ | app 镜像未发布：F 路径 ❌（等待 [FlagGems #5345](https://github.com/flagos-ai/FlagGems/pull/5345) 合入后重建） |
| DTK 26.04 | ⬜ | ⬜ | ⬜ | F 路径 ✅；app 镜像未发布：镜像侧 torch↔numpy ABI 不匹配（阻塞） |
| COREX 4.4.0 | ⬜ | ⬜ | ⬜ | F 路径 ❌：工具链代差（corex Triton 前端与 torch 2.7.1 落后于 vllm 要求，§2.5） |
| COREX 4.5.0 | ✅ | ✅ | ✅ | — |
| XRE 5.37.1 | ✅ | ✅ | ✅ | — |
| MACA 3.7.2.1 | ✅ | ✅ | ✅ | — |
| MACA 3.8.1.3 | ✅ | ✅ | ✅ | — |
| MUSA 4.3.6 | ✅ | ✅ | ✅ | — |
| MUSA 5.2.0 | ✅ | ✅ | ✅ | — |
| SPACEMIT | ⬜ | ⬜ | ⬜ | — |
| TANGRT 1.2.0 | ✅ | ✅ | ✅ | — |
| PPU 2.0.0 | ⬜ | ⬜ | ⬜ | — |
| TSM 260610 | ⬜ | ⬜ | ⬜ | — |


<!-- /status-matrix:facility:vllm0.20.2 -->

<!-- status-matrix:facility:vllm0.24.0 -->

### vllm0.24.0

> 数据截止：2026-08-31

**App 级设施（全后端共享）**

| 事项 | 状态 |
|---|---|
| Containerfile | ✅ |
| 构建 workflow | ✅ |

**后端级设施**

| 后端 | deps_app 落库 | 启动文档 | 镜像发布 | 备注 |
|---|---|---|---|---|
| CUDA 12.8 | ✅ | ✅ | ✅ | — |
| CUDA 13.3 | ✅ | ✅ | ✅ | — |
| CANN 8.5.0 | ✅ | ✅ | ✅ | — |
| CANN 9.0.0 | ✅ | ✅ | ✅ | — |
| NEUWARE 4.4.3 | ⬜ | ⬜ | ⬜ | — |
| NEUWARE 4.7.2 | ⬜ | ⬜ | ⬜ | — |
| TOPS 1.9.10 | ⬜ | ⬜ | ⬜ | — |
| TOPS 1.10.6 | ⬜ | ⬜ | ⬜ | — |
| DTK 26.04 | ✅ | ✅ | ⬜ | app 镜像暂不做（2026-08-20 决策）：F 路径等待 FlagTree 发布修复版本（flagtree hygon wheel 重建） |
| COREX 4.4.0 | ⬜ | ⬜ | ⬜ | — |
| COREX 4.5.0 | ✅ | ✅ | ✅ | — |
| XRE 5.37.1 | ✅ | ✅ | ✅ | — |
| MACA 3.7.2.1 | ✅ | ✅ | ⬜ | 验证 ✅，app 镜像未推送 Harbor |
| MACA 3.8.1.3 | ✅ | ✅ | ⬜ | 验证 ✅，app 镜像未推送 Harbor |
| MUSA 4.3.6 | ✅ | ✅ | ⬜ | 验证 ✅，app 镜像未推送 Harbor |
| MUSA 5.2.0 | ✅ | ✅ | ✅ | — |
| SPACEMIT | ⬜ | ⬜ | ⬜ | — |
| TANGRT 1.2.0 | ✅ | ✅ | ✅ | — |
| PPU 2.0.0 | ⬜ | ⬜ | ⬜ | — |
| TSM 260610 | ✅ | ✅ | ✅ | — |


<!-- /status-matrix:facility:vllm0.24.0 -->

## 编译器覆盖现状（configs.yaml 2026-08-15）

- **双编译器**（15 backend）：nvidia×2, ascend×2, enflame×2, hygon, iluvatar,
  kunlunxin, metax×2, mthreads×2, sunrise, tsingmicro。默认 flagtree，`compiler` 函数切换。
- **仅 triton**（4 backend）：cambricon×2, spacemit, thead。

## 后端 Python 版本（configs.yaml 2026-08-15）

0.24.0 empty wheel 绑定 CPython 小版本（`cp312-cp312`），
3.10/3.11 后端在 0.24.0 验证前须先按各自 Python 构建 wheel，不能复用 cp312 产物。

- **3.12**（10 backend）：nvidia×2, cambricon-neuware4.7.2, enflame×2, iluvatar,
  metax×2, spacemit, thead
- **3.11**（2 backend）：ascend-cann8.5.0, ascend-cann9.0.0
- **3.10**（7 backend）：cambricon-neuware4.4.3, hygon, kunlunxin, mthreads×2,
  sunrise, tsingmicro

## 已验证 / 已知事实

**0.20.2（截至 2026-08-26）**

- **nvidia-cuda12.8**（参考实现）：✅（2026-08-23，empty 模式 app 镜像
  F/T 双路径 E2E，吞吐一致 3.2 tok/s）—— [0.20.2 §2.1](vllm-0.20.2/backends/nvidia.md)。
- **metax-maca3.7.2.1**：✅ flagtree 0.6.1+metax3.6（基于 [FlagTree #1052](https://github.com/flagos-ai/FlagTree/pull/1052)；
  MACA SDK 内嵌 3.1.0 缺 API 否决）与 triton 3.0.0 均已入栈（T 路径的 flag_gems scalar 返回 bug 已由 flag_gems
  5.3.5 固化，2026-08-25 F/T 双路径复验 ✅）—— [0.20.2 §2.2](vllm-0.20.2/backends/metax.md)。
- **metax-maca3.8.1.3**：✅（2026-08-25 复验，triton 3.6.0 不受 scalar bug 影响）——
  同 [§2.2](vllm-0.20.2/backends/metax.md)。
- **mthreads-musa5.2.0**：✅ flagtree 0.6.0+mthreads3.6（验证时镜像 triton
  absent，由 flagtree 提供 triton API）—— [0.20.2 §2.3](vllm-0.20.2/backends/mthreads.md)。
- **hygon-dtk26.04**：✅ flagtree 0.5.1+hcu3.1，无 triton ——
  [0.20.2 §2.4](vllm-0.20.2/backends/hygon.md)。
- **iluvatar-corex4.4.0**：❌ 推理乱码（负结果）。根因：前向数值错误，torch
  2.7.1+corex 过旧；corex triton fork 下 vllm 原生 kernel 亦不可编译 ——
  [0.20.2 §2.5](vllm-0.20.2/backends/iluvatar.md)。
- **enflame（TOPS 1.9.10 / 1.10.6）**：T ✅（显式 `compiler triton`，vendor
  triton + 原生 FLASH_ATTN）；flagtree 不信任、不交付 → F ❌ ——
  [0.20.2 §2.6](vllm-0.20.2/backends/enflame.md)。
- **cambricon-neuware4.7.2**（MLU590）：✅（仅 triton）——
  [0.20.2 §2.7](vllm-0.20.2/backends/cambricon.md)。
- **ascend-cann9.0.0**（910B4，aarch64 cp311）：✅ flagtree 路径（修复
  flag_gems 5.3.4 `j0`/`log2` 后全链路跑通）—— [0.20.2 §2.8](vllm-0.20.2/backends/ascend.md)。
- **sunrise-tangrt1.2.0**：✅ 双编译器（官方 Triton ✅；flagtree decode 挂死
  由 [FlagTree #978](https://github.com/flagos-ai/FlagTree/pull/978) + rebuilt wheel 修复，2026-08-20 复测 0.20.2(F) 路径 ✅）——
  [0.20.2 §2.9](vllm-0.20.2/backends/sunrise.md)。
- **kunlunxin-xre5.37.1**（P800 XPU）：✅（2026-08-22~23）0.20.2 双编译器
  E2E —— flagtree 0.6.1+xpu3.6 7/7、triton 3.6.0 3/3。此前三处 attention
  内核编译失败由插件层 [VPF #268](https://github.com/flagos-ai/vllm-plugin-FL/pull/268)
  + triton 3.6.0 升级绕开；解码乱码（[VPF #400](https://github.com/flagos-ai/vllm-plugin-FL/pull/400)）、
  假死（`XPU_EVENT_KL3_ENABLE=1` 配方去掉）已闭环 ——
  [0.20.2 §2.10](vllm-0.20.2/backends/kunlunxin.md)。

**0.24.0（截至 2026-08-23）**

- **nvidia-cuda12.8 / cuda13.3**：✅✅（2026-08-16，空模式双编译器，指纹
  `vllm-0.24.0-423da8ca`；cp312 empty wheel 跨 CUDA 复用实测 ✅）——
  [0.24.0 §6](vllm-0.24.0/backends/nvidia.md)。
- **metax 四环境**：✅（2026-08-13~15，MACA 3.7.2.1 / 3.8.1.3 × 双编译器）。
  flagtree 3.1.0 否决（缺 API）改用 0.6.1+metax3.6；triton 3.0.0 需
  `vllm024_compat.py` 4 个 monkey-patch（老 SDK 特有）——
  [0.24.0 §4–§5](vllm-0.24.0/backends/metax.md)。
- **mthreads-musa5.2.0 / musa4.3.6**：✅✅（2026-08-16~17，v0.3.0-dev 零插件
  补丁，F/T 双路径；torchvision guard = 插件 [VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)）。
  4.3.6 验证模型为 DeepSeek-R1-0528-Qwen3-8B-FlagOS（该平台无
  Qwen3-4B，矩阵"Qwen3-4B"约定在此单元格不适用）——
  [0.24.0 §8–§9](vllm-0.24.0/backends/mthreads.md)。
- **ascend-cann9.0.0 / cann8.5.0**：✅✅（2026-08-17~18，插件 [VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387) 移植，
  双编译器 + app 镜像）—— [0.24.0 §10](vllm-0.24.0/backends/ascend.md)。
- **sunrise-tangrt1.2.0**：✅（2026-08-19，cp310 wheel + CUSTOM 移植；
  T 路径 + F 路径（rebuilt flagtree wheel）+ app 镜像）——
  [0.24.0 §11](vllm-0.24.0/backends/sunrise.md)。
- **hygon-dtk26.04**：✅✅（2026-08-20，cp310 wheel，F/T 双路径 TP2；flagtree
  0.6.1+hcu3.6 临时就地补 `cluster_dims` 默认值，[FlagTree #1020](https://github.com/flagos-ai/FlagTree/pull/1020) 上游修复）——
  [0.24.0 §12](vllm-0.24.0/backends/hygon.md)。
- **kunlunxin-xre5.37.1**：✅（2026-08-23，cp310 empty wheel + 插件 [VPF #401](https://github.com/flagos-ai/vllm-plugin-FL/pull/401)
  移植 + app 镜像 serve E2E，flagtree + triton 双编译器）——
  [0.24.0 §13](vllm-0.24.0/backends/kunlunxin.md)。
- **0.24.0 其余后端待验证**：iluvatar、enflame、cambricon。

**跨版本事实**

- 0.24.0 empty wheel 绑定 `cp312-cp312-linux_x86_64`，0.20.2 是 `py3-none-any`
  （纯 Python，可跨 cp 复用）。
- **cp312 wheel 跨 CUDA 版本可复用**（实测）：cuda12.8 构建的 `vllm-0.24.0+flagos`
  wheel 在 cuda13.3（torch 2.11.0+cu130）上单步安装运行 ✅。是否可跨 OS/架构
  （如 aarch64）仍待验证。
- 所有适配补丁收敛在 vllm-plugin-FL 插件侧，不修改官方 vLLM。
- **torchvision 依赖（0.24.0 通用 OOT 缺口）**：`kernel_warmup()` 无条件
  import minimax_m3_msa_warmup → torchvision，无 torchvision 后端首次 serve
  在 EngineCore init 崩溃；修复在插件调用侧（[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)，try/except skip）——
  [0.24.0 §9.4](vllm-0.24.0/backends/mthreads.md)。
- **`runtime/zz-compiler.sh` 修复**
  （[build-infra #411](https://github.com/flagos-ai/build-infra/pull/411)）："T 路径不可用"注记作废 ——
  裸 `compiler`（status）探测 `_compiler_import_triton` prepend 不清除已在
  PYTHONPATH 的 side dir 导致 entry-point 混叠，切换路径本身干净。
- **hygon flagtree wheel 待建**（[FlagTree #1020](https://github.com/flagos-ai/FlagTree/pull/1020) 合入后重建 `packaging/flagtree/hygon`，
  替换容器内临时 sed）；**hygon app 镜像暂不做**（2026-08-20 决策，见
  [0.24.0 §14](vllm-0.24.0/index.md)）。

## 已知问题 / 阻塞

- **sunrise**：flagtree flash-attn decode 挂死（已交 FlagTree 团队，[FlagTree #978](https://github.com/flagos-ai/FlagTree/pull/978)
  修复，2026-08-19 起 F 路径 ✅）；交付固定走官方 Triton。
- **iluvatar**：推理乱码根因在厂商工具链过旧（torch 2.7.1），非编译器层问题。
- **enflame**：策略性不用 flagtree（不信任），走 vendor triton + native FLASH_ATTN。

## 验证顺序建议

1. **0.24.0 nvidia-cuda12.8 先行**（参考实现）：确认 0.24.0 在 flagtree 下的基线行为。
2. **3.10 / 3.11 后端先补构建**：0.24.0 empty wheel 与 CPython 绑定，
   验证前需按后端 Python 版本构建对应 wheel。
3. **双编译器后端逐一对两编译器验证**：metax、mthreads、sunrise、hygon、
   kunlunxin 已全通；enflame 按风险排序推进。
4. **单编译器后端**（cambricon、spacemit、thead）：只需验证可用的一列。
5. **iluvatar**：等待上游修复后再列入验证队列。
