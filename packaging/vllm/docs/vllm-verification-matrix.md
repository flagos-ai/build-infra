# vllm repack 验证矩阵

> 规划工具，随验证推进更新。每单元格 = 对应后端 runtime 镜像 + `vllm X.Y.Z+flagos`
> 单步安装后，serve + 推理（Qwen3-4B）跑通的验证。
> 状态结论、根因与修复细节见 [`report-vllm-0.20.2.md`](report-vllm-0.20.2.md) 和
> [`report-vllm-0.24.0.md`](report-vllm-0.24.0.md)；本矩阵只记录状态。

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
| 昆仑芯 | XRE 5.37.1 | ✅ | ✅ | ✅ | ✅ |
| 沐曦 | MACA 3.7.2.1 | ✅ | ✅ | ✅ | ✅ |
| 沐曦 | MACA 3.8.1.3 | ✅ | ✅ | ✅ | ✅ |
| 摩尔线程 | MUSA 4.3.6 | ✅ | ✅ | ✅ | ✅ |
| 摩尔线程 | MUSA 5.2.0 | ✅ | ✅ | ✅ | ✅ |
| 进迭时空 | SPACEMIT | ⬜ | — | ⬜ | — |
| 曦望 | TANGRT 1.2.0 | ✅ | ✅ | ✅ | ✅ |
| 平头哥 | PPU 2.0.0 | ⬜ | — | ⬜ | — |
| 清微智能 | TSM 260610 | ⬜ | ⬜ | ⬜ | ⬜ |

**后端级上游 PR（验证/镜像基于 PR 分支 Head 的跟踪项）**

| 厂商 | 后端 | App | PR |
|---|---|---|---|
| 昇腾 | CANN 8.5.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/361 |
| 昇腾 | CANN 8.5.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/402 |
| 昇腾 | CANN 8.5.0 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/387 |
| 昇腾 | CANN 9.0.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/361 |
| 昇腾 | CANN 9.0.0 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/402 |
| 昇腾 | CANN 9.0.0 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/387 |
| 寒武纪 | NEUWARE 4.4.3 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/355 |
| 寒武纪 | NEUWARE 4.4.3 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5745 |
| 寒武纪 | NEUWARE 4.7.2 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/355 |
| 寒武纪 | NEUWARE 4.7.2 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5745 |
| 寒武纪 | NEUWARE 4.7.2 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5510 |
| 燧原 | TOPS 1.9.10 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5345 |
| 燧原 | TOPS 1.10.6 | vllm0.20.2 | https://github.com/flagos-ai/FlagGems/pull/5345 |
| 海光 | DTK 26.04 | vllm0.24.0 | https://github.com/flagos-ai/FlagTree/pull/1020 |
| 昆仑芯 | XRE 5.37.1 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/268 |
| 昆仑芯 | XRE 5.37.1 | vllm0.20.2 | https://github.com/flagos-ai/vllm-plugin-FL/pull/400 |
| 昆仑芯 | XRE 5.37.1 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/401 |
| 摩尔线程 | MUSA 4.3.6 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/386 |
| 摩尔线程 | MUSA 4.3.6 | vllm0.24.0 | https://github.com/flagos-ai/FlagGems/pull/5130 |
| 摩尔线程 | MUSA 5.2.0 | vllm0.24.0 | https://github.com/flagos-ai/vllm-plugin-FL/pull/386 |
| 摩尔线程 | MUSA 5.2.0 | vllm0.24.0 | https://github.com/flagos-ai/FlagGems/pull/5130 |
| 曦望 | TANGRT 1.2.0 | vllm0.20.2 | https://github.com/flagos-ai/FlagTree/pull/978 |
| 曦望 | TANGRT 1.2.0 | vllm0.24.0 | https://github.com/flagos-ai/FlagTree/pull/978 |

<!-- /status-matrix:verification -->

## 设施落地

> 数据驱动自 `packaging/vllm/status_matrix.*.yaml`（schema 与刷新机制见
> docs/status-matrix.md）。deps_app 落库 = configs.yaml 的 deps_app key 存在
> （该 backend 可构建此 app）；镜像发布 = 该 app 镜像已推送 Harbor。

<!-- status-matrix:facility:vllm0.20.2 -->

### vllm0.20.2

> 数据截止：2026-08-26

**App 级设施（全后端共享）**

| 事项 | 状态 |
|---|---|
| Containerfile | ✅ |
| 构建 workflow | ✅ |

**后端级设施**

| 后端 | deps_app 落库 | 启动文档 | 镜像发布 |
|---|---|---|---|
| CUDA 12.8 | ✅ | ✅ | ✅ |
| CUDA 13.3 | ✅ | ✅ | ✅ |
| CANN 8.5.0 | ✅ | ✅ | ✅ |
| CANN 9.0.0 | ✅ | ✅ | ✅ |
| NEUWARE 4.4.3 | ✅ | ✅ | ✅ |
| NEUWARE 4.7.2 | ✅ | ✅ | ✅ |
| TOPS 1.9.10 | ✅ | ✅ | ⬜ |
| TOPS 1.10.6 | ✅ | ✅ | ⬜ |
| DTK 26.04 | ⬜ | ⬜ | ⬜ |
| COREX 4.4.0 | ⬜ | ⬜ | ⬜ |
| XRE 5.37.1 | ✅ | ✅ | ⬜ |
| MACA 3.7.2.1 | ✅ | ✅ | ✅ |
| MACA 3.8.1.3 | ✅ | ✅ | ✅ |
| MUSA 4.3.6 | ✅ | ✅ | ✅ |
| MUSA 5.2.0 | ✅ | ✅ | ✅ |
| SPACEMIT | ⬜ | ⬜ | ⬜ |
| TANGRT 1.2.0 | ✅ | ✅ | ✅ |
| PPU 2.0.0 | ⬜ | ⬜ | ⬜ |
| TSM 260610 | ⬜ | ⬜ | ⬜ |


<!-- /status-matrix:facility:vllm0.20.2 -->

<!-- status-matrix:facility:vllm0.24.0 -->

### vllm0.24.0

> 数据截止：2026-08-23

**App 级设施（全后端共享）**

| 事项 | 状态 |
|---|---|
| Containerfile | ✅ |
| 构建 workflow | ✅ |

**后端级设施**

| 后端 | deps_app 落库 | 启动文档 | 镜像发布 |
|---|---|---|---|
| CUDA 12.8 | ✅ | ✅ | ✅ |
| CUDA 13.3 | ✅ | ✅ | ⬜ |
| CANN 8.5.0 | ✅ | ✅ | ✅ |
| CANN 9.0.0 | ✅ | ✅ | ✅ |
| NEUWARE 4.4.3 | ⬜ | ⬜ | ⬜ |
| NEUWARE 4.7.2 | ⬜ | ⬜ | ⬜ |
| TOPS 1.9.10 | ⬜ | ⬜ | ⬜ |
| TOPS 1.10.6 | ⬜ | ⬜ | ⬜ |
| DTK 26.04 | ✅ | ✅ | ⬜ |
| COREX 4.4.0 | ⬜ | ⬜ | ⬜ |
| XRE 5.37.1 | ✅ | ✅ | ✅ |
| MACA 3.7.2.1 | ✅ | ✅ | ⬜ |
| MACA 3.8.1.3 | ✅ | ✅ | ⬜ |
| MUSA 4.3.6 | ✅ | ✅ | ⬜ |
| MUSA 5.2.0 | ✅ | ✅ | ⬜ |
| SPACEMIT | ⬜ | ⬜ | ⬜ |
| TANGRT 1.2.0 | ✅ | ✅ | ✅ |
| PPU 2.0.0 | ⬜ | ⬜ | ⬜ |
| TSM 260610 | ⬜ | ⬜ | ⬜ |


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

**0.20.2（截至 2026-08-11）**

- **nvidia-cuda12.8**（参考实现）：✅（2026-08-23，empty 模式 app 镜像
  `vllm0.20.2-nvidia-cuda12.8:2.1.2-0.2.1_g825c1cd`）F/T 双路径各跑一遍 E2E
  —— F 路径（flagtree，默认 CMD）✅、T 路径（triton 3.6.0，`PYTHONPATH=/opt/triton`
  显式切换）✅，同一 Qwen3-4B prompt 输出连贯、吞吐一致（3.2 tok/s）。
  此前 2026-08-16 双编译器验证在 vendor（standard）vllm 镜像上完成，与 empty
  产物非同镜像，不背书 empty 结果（详见 `report-vllm-0.20.2.md` §2.1）。
- **metax-maca3.7.2.1**：flagtree **3.1.0+metax3.7.2.0**（厂商自带）✅，
  configs 现为 0.6.1+metax3.6；triton 3.0.0 未单独验证。
- **mthreads-musa5.2.0**：flagtree 0.6.0+mthreads3.6 ✅；
  验证时镜像 triton absent（由 flagtree 提供 triton API）。
- **hygon-dtk26.04**：flagtree **0.5.1+hcu3.1** ✅，configs 现为 0.6.1+hcu3.6；
  无 triton。
- **iluvatar-corex4.4.0**：❌ 推理乱码（负结果）。根因：前向数值错误，
  torch 2.7.1+corex 过旧；corex triton fork 下 vllm 原生 kernel 亦不可编译。
- **enflame（TOPS 1.9.10 / 1.10.6）**：显式 `compiler triton`（vendor triton）✅，
  走 vLLM 原生 FLASH_ATTN；**flagtree 不信任，不交付** → F 列 ❌。
- **cambricon-neuware4.7.2**（MLU590）：仅 triton，✅ E2E。
- **ascend-cann9.0.0**（910B4，aarch64 cp311）：flagtree 路径 ✅
  （修复 flag_gems 5.3.4 `j0`/`log2` 后全链路跑通）；triton 路径未单独验证。
- **sunrise-tangrt1.2.0**：官方 Triton ✅；flagtree flash-attn **decode 挂死** ❌，
  交付路径固定 `compiler triton`。（该缺陷 2026-08-19 起已由 rebuilt
  flagtree wheel 修复 —— 0.24.0 中 F 路径 ✅，见下方 0.24.0 格与
  `report-vllm-0.24.0.md` §11.5；**2026-08-20 在 rebuilt wheel 下复测
  0.20.2(F) 路径 ✅**——serve 达 `Application startup complete`、推理连贯
  （knowledge "Paris" / math "56"）、decode 正常终止，本格翻 ✅。）
- **kunlunxin-xre5.37.1**（P800 XPU）：✅（2026-08-22~23）0.20.2 双编译器 E2E
  通过 —— flagtree 0.6.1+xpu3.6 **7/7**（7.3~9.8 tok/s）、triton 3.6.0 **3/3**
  （5.7~7.3 tok/s），serve + 推理连贯。此前三处 attention 内核编译失败
  （flagtree `TritonSDNNLegalize` / `TritonSDNNCombineBefore`、triton 3.0.0
  XTDK LLVM19 空 SetVector 断言）由厂商插件层 **PR #268**（xtorch_ops 原生
  attention backend，不碰 Triton 编译）+ triton 3.6.0 升级（#469）绕开，
  详见 [kunlunxin-xpu-triton-attention-compiler-bug.md](kunlunxin-xpu-triton-attention-compiler-bug.md)。
  验证中另两个问题（解码乱码 = 插件 patch scale 传错，修复已上提 PR #400；
  假死 = `XPU_EVENT_KL3_ENABLE=1` 触发，配方去掉该行）均已闭环，详见
  [kunlunxin-decode-repetition-scale-bug.md](kunlunxin-decode-repetition-scale-bug.md)。

**0.24.0（截至 2026-08-20）**

- **nvidia-cuda12.8** ✅（2026-08-16，空模式双编译器）：flagtree 3.6.0 ✅、
  triton 3.6.0 ✅（`/opt/triton`），均通过 Qwen3-4B E2E 验证，指纹 `vllm-0.24.0-423da8ca`。
- **nvidia-cuda13.3** ✅（2026-08-16，空模式双编译器）：flagtree 3.6.0 ✅、
  triton 3.6.0 ✅，均通过 Qwen3-4B E2E 验证，指纹 `vllm-0.24.0-423da8ca`。
  同时验证了 **cp312 empty wheel 跨 CUDA 复用**：12.8（torch 2.10.0+cu128）构建的
  同一 Wheel 直接在 13.3（torch 2.11.0+cu130）上安装运行。
- **NVIDIA 路径统一要点**（详见 `report-vllm-0.24.0.md` §6）：
  插件基线 **v0.3.0-dev**；CUDA 平台无条件 import flashinfer，
  需环境变量 `VLLM_USE_FLASHINFER_SAMPLER=0` 关闭采样器；
  插件安装必须 `--no-build-isolation`（构建隔离会从 pypi.org 下载 torch≈2.4GB）。
- **metax 四环境全 ✅**（2026-08-13~15）：MACA 3.7.2.1
  （triton 3.0.0 / flagtree 0.6.1+metax3.6）× 两编译器、MACA 3.8.1.3
  （triton 3.6.0 / flagtree 0.6.1+metax3.6）× 两编译器。
- **flagtree 3.1.0 否决**（0.24.0）：缺 `do_not_specialize_on_alignment` 参数 +
  缺 `knobs` 模块，改用 0.6.1+metax3.6。
- **triton 3.0.0 需 4 个 monkey-patch**（`vllm024_compat.py`，老 SDK 特有）：
  `_load_ptr` constexpr 解包、`_penalties_kernel` 链式布尔加括号、
  `get_top_k_top_p` 与 `pool` 的 UVA CPU 索引 + 移回设备；新 SDK（triton 3.6.0）无需。
- **0.24.0 其余后端待验证**：iluvatar, enflame,
  cambricon, kunlunxin 等。
- **mthreads-musa5.2.0** ✅✅（2026-08-16~17，v0.3.0-dev 零插件补丁）：
  F 路径 ✅（2026-08-16，默认 flagtree 3.6.0）+ T 路径 ✅（2026-08-17，
  `compiler triton` → vendor triton 3.6.0，musa backend）。两条路径均
  OpManager 10 ops/14 impls、attention fallback `vendor.musa`、serve 到
  `Application startup complete`、推理连贯。
  **注意：验证模型为 DeepSeek-R1-0528-Qwen3-8B-FlagOS**（mthreads 节点无
  Qwen3-4B），矩阵"Qwen3-4B"约定在此单元格不适用，详见
  `report-vllm-0.24.0.md` §8。
  **serve 期的 torchvision 依赖经节点侧就地 patch 绕过（不可复现）**：
  该次 `kernel_warmup` 崩溃被就地改写 `kernel_warmup.py` 绕过，非 wheel
  内建能力；可复现修复 = 插件 guard（PR #386），见跨版本事实。
  **早期 "T 路径不可用" 注记作废**：`No module named 'triton.backends.mthreads'`
  是裸 `compiler`（status）探测的 bug —— `_compiler_import_triton` prepend
  不清除已在 PYTHONPATH 的另一个 side dir，导致 entry-point 混叠
  （flagtree 声明 `mthreads` backend、/opt/triton 声明 `musa`），
  切换路径本身干净。已修 `runtime/zz-compiler.sh`（PR #411）。
- **mthreads-musa4.3.6**（2026-08-17，v0.3.0-dev + 插件 torchvision guard，python 3.10）：
  **T 路径 ✅** —— `compiler triton` → vendor triton 3.6.0+git89458660，
  同一 pow 内核编译通过，serve 到 `Application startup complete`、推理连贯，
  指纹 `vllm-0.24.0-5936039f`（5.2.0 为 `vllm-0.24.0-423da8ca`）。
  验证模型同为 DeepSeek-R1-0528-Qwen3-8B-FlagOS（矩阵"Qwen3-4B"约定
  在此单元格不适用，同 §8）。
  **F 路径 ✅（flagtree 0.6.1 烘焙镜像，重建后复验）**：configs bump
  （PR #414）已合并、镜像已重建（0.6.1+mthreads3.6 烘焙于
  `/opt/flagtree`）。重建镜像 F 路径（`compiler flagtree`）serve 到
  `Application startup complete`、completions greedy + chat CoT 均连贯、
  指纹 `vllm-0.24.0-5936039f`，同 T 路径。0.6.0→0.6.1 即 pow 内核修复
  （`v2f32 = fexp2`，见 `report-vllm-0.24.0.md` §9.3）。
  **torchvision guard（插件 PR #386）为本次 F 路径 serve 的前置**：重建镜像
  新容器首次 serve 因 vllm 0.24.0 `kernel_warmup` 无条件 import
  minimax_m3_msa_warmup → torchvision（OOT runtime 不装）而崩；
  早期 4.3.6/5.2.0 serve 成功依赖节点侧就地 patch（不可复现）。修复落在
  插件调用侧，详见 §9.4 与跨版本事实。
- **ascend-cann9.0.0** ✅✅（2026-08-17~18，v0.3.0-dev + 插件 PR #387
  移植）：flagtree 0.6.1+ascend3.5 路径 ✅（2026-08-17）—— Qwen3-4B
  TP1 serve 到 `Application startup complete`、推理连贯（knowledge
  "Paris" / math "56"），指纹 `vllm-0.24.0-563743c8`；triton 路径 ✅
  （2026-08-18，hw25，`/opt/triton` = triton 3.5.0 + triton_ascend
  3.2.1 overlay，`triton.__version__` = 3.2.0）—— 同参数 serve 到
  `Application startup complete`、推理连贯、崩溃标记 0，指纹
  `vllm-0.24.0-0535d777`。两路径 `rms_norm`/`rotary_embedding` 均走
  `vendor.ascend`，`silu_and_mul` 回退 `default.flagos`。移植内容与
  0.24.0 定制见 `report-vllm-0.24.0.md` §10。
  **app 镜像路径 ✅**（2026-08-18，hw25）：`vllm-ascend-cann9.0.0:2.1.2`
  （wheel 单步安装：vllm `0.24.0+flagos` + vllm-plugin-fl
  `0.2.0+gcf8998c.d20260818`，`vllm-serve` launcher）serve 到
  `Application startup complete`、推理连贯、崩溃标记 0，指纹
  `vllm-0.24.0-0535d777`（同一 wheel）。详见 report §10.5。
- **ascend-cann8.5.0** ✅（2026-08-18，hw26）：flagtree 0.6.0+ascend3.2
  与 triton_ascend 3.2.0 双编译器路径全绿 —— Qwen3-4B TP1 serve 到
  `Application startup complete`、推理连贯（knowledge "Paris" / math
  "56"），崩溃标记 0。triton 路径需 `linear`/`pow`/`cumsum`/
  `repeat_interleave` 黑名单（插件 commit `cf8998c`；triton_ascend
  3.2.0 decode GEMM 死转，详见 `report-vllm-0.24.0.md` §10.3）。
- **sunrise-tangrt1.2.0** ✅（2026-08-19，cp310 wheel + 插件 CUSTOM
  移植）：**T 路径 ✅** —— `compiler triton` → vendor triton
  3.6.0.1+git0a5cfb35，Qwen3-8B TP1 serve 到 `Application startup
  complete`、推理连贯，指纹 `vllm-0.24.0-6c831be5`。前置 = cp310
  empty wheel（sunrise 是 python 3.10，0.24.0 wheel 绑定 CPython 小
  版本）+ 插件两条改动：attention backend 改 **CUSTOM 注册**
  （ascend PR #387 同款模式）+ `patch_accelerator_memory_stats()`
  （合成 `torch.ptpu.memory_stats()` 供 FL worker KV-cache 定容，
  首次 serve 曾崩 `AttributeError: no attribute 'memory_stats'`）。
  详见 `report-vllm-0.24.0.md` §11。
  **F 路径 ✅（2026-08-19，rebuilt flagtree wheel）** —— 旧 §2.9
  decode 挂死由 FlagTree PR 978 修复（`packaging/flagtree/sunrise`
  从 main 重建 wheel，A/B 0.4 → 2.4 tok/s 终止），`compiler flagtree`
  serve + 推理 E2E 通过（§11.5）。
  **app 镜像路径 ✅（§11.6）**：`flagos-app/vllm0.24.0-sunrise-
  tangrt1.2.0:2.1.2-0.2.0_g687217a.d20260819`（wheel 单步安装 + plugin
  wheel）serve 到 `Application startup complete`、推理连贯、崩溃标记
  0，指纹 `vllm-0.24.0-6c831be5`（同一 wheel）。
- **hygon-dtk26.04** ✅✅（2026-08-20，cp310 wheel）：**T 路径 ✅** ——
  `compiler triton` → vendor triton 3.5.1，**F 路径 ✅** —— flagtree
  0.6.1+hcu3.6（临时就地补 `cluster_dims` 默认值，FlagTree PR #1020
  上游修复，见下）。模型 `/data/Sky-T1-32B-Preview-FlagOS`（Sky-T1
  32B，Qwen2 架构；矩阵"Qwen3-4B"约定在此单元格不适用，同 §8/§11.3
  先例）。两路径均 TP2 serve 到 `Application startup complete`、推理
  连贯（knowledge "Paris" / math "42"）、崩溃标记 0、指纹
  `vllm-0.24.0-tp2-5c23ce1f`（tp2 后缀 = tensor-parallel-size 2），
  算子路由全 `default.flagos`。版本指纹：torch
  2.9.0+das.opt1.dtk2604 / flag_gems 5.3.4 / vllm-plugin-fl
  0.2.0+g754c8fe23。详见 `report-vllm-0.24.0.md` §12。
  **`cluster_dims` 修复**：flagtree `CompiledKernel.__init__` 构造
  `KernelMetadata` 时 hcu/mthreads 后端不产出 `cluster_dims` key，
  torch 2.9.0 `make_launcher` 无条件读取 → 首次 serve KV-cache
  warmup 崩 AttributeError。修复 = 一行 `setdefault("cluster_dims",
  (1,1,1))`，FlagTree PR #1020；容器内临时 sed 解锁验证，可复现修复
  = PR 合入后重建 flagtree hygon wheel（`packaging/flagtree/hygon`，
  待建）。
  **hygon app 镜像：暂不做（2026-08-20 决策，见 report §14）** ——
  F 路径默认编译器被 PR #1020 合入 + flagtree hygon wheel 重建卡死
  （无新 flagtree release 前 runtime 无法刷新）；T 路径（vendor
  triton 3.5.1 已在 runtime）技术上可做，同轮交付意义不大，PR
  合入后重估。

**跨版本事实**

- 0.24.0 empty wheel 绑定 `cp312-cp312-linux_x86_64`，
  0.20.2 是 `py3-none-any`（纯 Python，可跨 cp 复用）。
- **cp312 wheel 跨 CUDA 版本可复用**（实测）：cuda12.8 构建的 `vllm-0.24.0+flagos`
  wheel 在 cuda13.3（torch 2.11.0+cu130）上单步安装运行 ✅。
  是否可跨 OS/架构（如 aarch64）仍待验证。
- 所有适配补丁收敛在 vllm-plugin-FL 插件侧，不修改官方 vLLM。
- **torchvision 依赖（0.24.0 通用 OOT 缺口）**：`kernel_warmup()` 无条件
  import minimax_m3_msa_warmup → torchvision。OOT runtime（cambricon×2、
  hygon、ascend×2、mthreads×2）不装 torchvision（会覆盖厂商 torch 矩阵），
  因此 vllm 0.24.0 在全部无 torchvision 后端首次 serve 都会在 EngineCore
  init 崩溃。修复在插件调用侧（PR #386，`try/except ImportError` skip，
  warmup 对 MiniMaxM3 以外的模型是 no-op）。详见 `report-vllm-0.24.0.md` §9.4。

## 已知问题 / 阻塞

- **kunlunxin**：0.20.2 线已闭环（2026-08-22~23，见上）；0.24.0 线 upstream main
  已删除 vendor/kunlunxin 目录，插件无挂点。**0.24.0 可行性审计完成（2026-08-23，
  cp310 empty wheel + 插件移植范围已枚举，见 `report-vllm-0.24.0.md` §13），
  验证未开始。**
- **sunrise**：flagtree flash-attn decode 挂死，已交 FlagTree 团队；
  交付固定走官方 Triton。
- **iluvatar**：推理乱码根因在厂商工具链过旧（torch 2.7.1），非编译器层问题。
- **enflame**：策略性不用 flagtree（不信任），走 vendor triton + native FLASH_ATTN。

## 验证顺序建议

1. **0.24.0 nvidia-cuda12.8 先行**（参考实现）：确认 0.24.0 在 flagtree 下的基线行为。
2. **3.10 / 3.11 后端先补构建**：0.24.0 empty wheel 与 CPython 绑定，
   验证前需按后端 Python 版本构建对应 wheel。
3. **双编译器后端逐一对两编译器验证**：metax 已全通；mthreads 5.2.0 已全通
   （F/T 双路径）、4.3.6 T 路径 ✅ / F 路径 ✅*（flagtree 0.6.1，见上）；
   sunrise ✅（§11）、hygon ✅（§12，2026-08-20）；enflame 按风险排序推进。
4. **单编译器后端**（cambricon、spacemit、thead）：只需验证可用的一列。
5. **iluvatar**：等待上游修复后再列入验证队列（kunlunxin 0.20.2 已 ✅，见上）。
