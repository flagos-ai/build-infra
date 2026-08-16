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

| 厂商 | 后端 | 0.20.2(T) | 0.20.2(F) | 0.24.0(T) | 0.24.0(F) |
|---|---|---|---|---|---|
| 英伟达 | CUDA 12.8 | ⬜ | ✅ | ✅ | ✅ |
| 英伟达 | CUDA 13.3 | ⬜ | ⬜ | ✅ | ✅ |
| 昇腾 | CANN 8.5.0 | ⬜ | ⬜ | ⬜ | ⬜ |
| 昇腾 | CANN 9.0.0 | ⬜ | ✅ | ⬜ | ⬜ |
| 寒武纪 | NEUWARE 4.4.3 | ⬜ | — | ⬜ | — |
| 寒武纪 | NEUWARE 4.7.2 | ✅ | — | ⬜ | — |
| 燧原 | TOPS 1.9.10 | ✅ | ❌ | ⬜ | ⬜ |
| 燧原 | TOPS 1.10.6 | ✅ | ❌ | ⬜ | ⬜ |
| 海光 | DTK 26.04 | — | ✅ | ⬜ | ⬜ |
| 天数智芯 | COREX 4.4.0 | ⬜ | ❌ | ⬜ | ⬜ |
| 昆仑芯 | XRE 5.37.1 | ⛔ | ⛔ | ⬜ | ⬜ |
| 沐曦 | MACA 3.7.2.1 | ⬜ | ✅ | ✅ | ✅ |
| 沐曦 | MACA 3.8.1.3 | ⬜ | ⬜ | ✅ | ✅ |
| 摩尔线程 | MUSA 4.3.6 | ⬜ | ⬜ | ⬜ | ⬜ |
| 摩尔线程 | MUSA 5.2.0 | — | ✅ | ⬜ | ⬜ |
| 进迭时空 | SPACEMIT | ⬜ | — | ⬜ | — |
| 曦望 | TANGRT 1.2.0 | ✅ | ❌ | ⬜ | ⬜ |
| 平头哥 | PPU 2.0.0 | ⬜ | — | ⬜ | — |
| 清微智能 | TSM 260610 | ⬜ | ⬜ | ⬜ | ⬜ |

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

- **nvidia-cuda12.8**（参考实现）：flagtree 0.6.0（当时默认）✅；
  triton 3.6.0 并装于 `/opt/triton`，未单独验证。
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
  交付路径固定 `compiler triton`。
- **kunlunxin-xre5.37.1**（P800 XPU）：⛔ 三处 attention 内核编译失败——
  flagtree 0.6.1+xpu3.6（`TritonSDNNLegalize` / `TritonSDNNCombineBefore`）、
  triton 3.0.0（XTDK LLVM19 空 SetVector 断言）。应用层无法绕过，已交编译器团队，
  详见 [kunlunxin-xpu-triton-attention-compiler-bug.md](kunlunxin-xpu-triton-attention-compiler-bug.md)。

**0.24.0（截至 2026-08-16）**

- **nvidia-cuda12.8** ✅（2026-08-16，空模式双编译器）：flagtree 3.6.0 ✅、
  triton 3.6.0 ✅（`/opt/triton`），均 Qwen3-4B E2E，指纹 `vllm-0.24.0-423da8ca`。
- **nvidia-cuda13.3** ✅（2026-08-16，空模式双编译器）：flagtree 3.6.0 ✅、
  triton 3.6.0 ✅，均 Qwen3-4B E2E，指纹 `vllm-0.24.0-423da8ca`。
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
- **0.24.0 其余后端待验证**：mthreads, hygon, iluvatar, enflame, sunrise,
  cambricon, ascend, kunlunxin 等。

**跨版本事实**

- 0.24.0 empty wheel 绑定 `cp312-cp312-linux_x86_64`，
  0.20.2 是 `py3-none-any`（纯 Python，可跨 cp 复用）。
- **cp312 wheel 跨 CUDA 版本可复用**（实测）：cuda12.8 构建的 `vllm-0.24.0+flagos`
  wheel 在 cuda13.3（torch 2.11.0+cu130）上单步安装运行 ✅。
  是否可跨 OS/架构（如 aarch64）仍待验证。
- 所有适配补丁收敛在 vllm-plugin-FL 插件侧，不修改官方 vLLM。

## 已知问题 / 阻塞

- **kunlunxin**：attention 内核编译失败需编译器侧修复
  （TritonSDNN pass 链 / XTDK 后端断言），应用层无法绕过。
- **sunrise**：flagtree flash-attn decode 挂死，已交 FlagTree 团队；
  交付固定走官方 Triton。
- **iluvatar**：推理乱码根因在厂商工具链过旧（torch 2.7.1），非编译器层问题。
- **enflame**：策略性不用 flagtree（不信任），走 vendor triton + native FLASH_ATTN。

## 验证顺序建议

1. **0.24.0 nvidia-cuda12.8 先行**（参考实现）：确认 0.24.0 在 flagtree 下的基线行为。
2. **3.10 / 3.11 后端先补构建**：0.24.0 empty wheel 与 CPython 绑定，
   验证前需按后端 Python 版本构建对应 wheel。
3. **双编译器后端逐一对两编译器验证**：metax 已全通；mthreads、hygon、enflame、
   sunrise 等按风险排序推进。
4. **单编译器后端**（cambricon、spacemit、thead）：只需验证可用的一列。
5. **kunlunxin / iluvatar**：等待上游修复后再列入验证队列。
