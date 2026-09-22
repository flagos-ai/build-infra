# vllm 0.20.2 repack — 端到端验证报告

> **原则：上游 PR 不自 merge，review 期间用 PR head 推进制品。**
> 提给上游仓库的 PR 由各自维护团队合并。
> 为保证 review 期间不阻塞，用 PR head 构建 wheel → 验证 → 打镜像（版本指向
> PR head commit）；PR 合并后重走一遍流程产出定稿制品。中间 PR-head 制品只用于
> 推进验证，不作为发布件。

## 0. 背景

vLLM 原生 wheel 包中包含对 Torch、Triton 等关键软件包的声明式依赖。
如果不作处理，把 vllm 安装到 FlagOS runtime 环境时，
会覆盖现有环境中精心匹配、反复验证过的版本矩阵——
例如带入非厂商支持的 Torch 或 Triton 版本。
vLLM 所声明的其他间接依赖包中也存在同类问题（实际验证过程中已证实）。

因此，需要对 vLLM 及其声明依赖中"危险的"软件包进行预处理，或称重新打包
（repack），去除会破坏环境的依赖声明。重新打包后的 vLLM（及所牵涉的其他
Wheel）上传到 resource.flagos.net 的 Vendor PyPI 服务器，供流程化验证使用。

> **术语：`+flagos`** —— repack 后为 wheel 版本号追加的 PEP 440 本地版本
> 后缀（如 `0.20.2` → `0.20.2+flagos`）。它是"这个 wheel 出自 FlagOS repack
> 流程"的显式标记，也是单步安装能稳定命中我们的包的关键（见 [§1.4](playbook.md)、
> [§5.1](decisions.md)）。

---

## 文档结构

本目录按职责拆分验证报告，替代原单文件 `report-vllm-0.20.2.md`：

| 文件 | 内容 |
|---|---|
| [`playbook.md`](playbook.md) | 第 1 部分 · 标准流程（empty 构建 + `+flagos` + 单步安装）|
| [`decisions.md`](decisions.md) | 自动化边界（§3）、风险与痛点（§4）、ADR（§5）|
| `backends/` | 第 2 部分 · 后端验证记录（worked examples）|

后端记录按第 1 部分的模板组织：**环境 → repack → 安装 → 阻塞点 → Stack
验证 → 待办**。标准流程（[playbook.md](playbook.md)）即从这些记录中提炼；
记录里保留了个别后端走过的弯路，并标注哪些已被 playbook 取代。

### 后端索引

| 后端 | 文件 | 要点 |
|---|---|---|
| NVIDIA cuda12.8 / cuda13.3 | [nvidia.md](backends/nvidia.md) | 首个标准构建后端；2026-08-23 empty 复核 F/T 双路径 |
| MetaX maca3.7.2.1 | [metax.md](backends/metax.md) | 首个 empty 后端；3.8.1.3 复验见同文件 |
| mthreads musa4.3.6 / 5.2.0 | [mthreads.md](backends/mthreads.md) | 标准流程范例来源；mul 门控 [FlagGems #5130](https://github.com/flagos-ai/FlagGems/pull/5130) |
| hygon dtk26.04 | [hygon.md](backends/hygon.md) | §2.4 首个复用他机 wheel 后端（torch↔numpy ABI）；§2.15 app 镜像 F/T 双路径 |
| iluvatar corex4.4.0 / 4.5.0 | [iluvatar.md](backends/iluvatar.md) | 4.4.0 乱码（工具链过旧）；4.5.0 ✅ F/T 双路径 E2E |
| enflame tops1.9.10 / 1.10.6 | [enflame.md](backends/enflame.md) | GCU300 ✅ E2E；vLLM 原生 FLASH_ATTN |
| cambricon neuware4.7.2 | [cambricon.md](backends/cambricon.md) | §2.7 MLU590 主记录 |
| ascend cann9.0.0 | [ascend.md](backends/ascend.md) | 910B4 aarch64 cp311；fork-SHA 溯源表 |
| sunrise tangrt1.2.0 | [sunrise.md](backends/sunrise.md) | FlagTree decode 挂死 → 已修复（[FlagTree #978](https://github.com/flagos-ai/FlagTree/pull/978)）|
| kunlunxin xre5.37.1 | [kunlunxin.md](backends/kunlunxin.md) | P800 XPU；解码乱码 [VPF #400](https://github.com/flagos-ai/vllm-plugin-FL/pull/400) + 假死 KL3 |
| cambricon neuware4.4.3 | [cambricon.md](backends/cambricon.md) | §2.11，T-only 兼容 shim ×5 |
| tsingmicro tsm260610 | [tsingmicro.md](backends/tsingmicro.md) | §2.14，TX8110 F/T 双路径 E2E |

---

## 0.20.2 在 2.2.0 栈上的发布快照

2026-09-20，0.20.2 线在 FlagOS **2.2.0** 栈上全部重建完成：
20 个有 app 镜像的后端统一为 `2.2.0-0.2.2rc2.post2`（plugin
`vllm-plugin-FL v0.2.2-rc2.post2`），逐个通过 on-node verify
（包矩阵比对 + vllm/vllm_fl import + 真实 serve 出 token）后推送。
`packaging/vllm/status_matrix.vllm0.20.2.yaml` 是逐后端 tag 的权威记录。

| 后端 | FlagTree | image tag | 镜像+验证 |
|---|---|---|---|
| nvidia-cuda12.8 | 0.7.0rc2 | 2.2.0-0.2.2rc2.post2 | ✅ |
| nvidia-cuda13.3 | 0.6.1 | 2.2.0-0.2.2rc2.post2 | ✅ |
| ascend-cann8.5.0 | 0.6.0+ascend3.2 | 2.2.0-0.2.2rc2.post2 | ✅ |
| ascend-cann8.5.0-910c | 0.6.0+ascend3.2 | 2.2.0-0.2.2rc2.post2 | ✅ |
| ascend-cann9.0.0 | 0.7.0rc2+ascend3.5 | 2.2.0-0.2.2rc2.post2 | ✅ |
| ascend-cann9.0.0-910c | 0.7.0rc2+ascend3.5 | 2.2.0-0.2.2rc2.post2 | ✅ |
| cambricon-neuware4.4.3 | —（无 FlagTree） | 2.2.0-0.2.2rc2.post2 | ✅ |
| cambricon-neuware4.7.2 | —（无 FlagTree） | 2.2.0-0.2.2rc2.post2 | ✅ |
| enflame-tops1.9.10 | 0.6.0+enflame3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| enflame-tops1.10.6 | 0.7.0rc2+enflame3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| hygon-dtk26.04 | 0.7.0rc2+hcu3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| iluvatar-corex4.4.0 | 0.7.0rc2+iluvatar3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| iluvatar-corex4.5.0 | 0.7.0rc2+iluvatar3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| kunlunxin-xre5.37.1 | 0.7.0rc2+xpu3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| metax-maca3.7.2.1 | 0.6.1+metax3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| metax-maca3.8.1.3 | 0.6.1+metax3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| mthreads-musa4.3.6 | 0.7.0rc2+mthreads3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| mthreads-musa5.2.0 | 0.7.0rc2+mthreads3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| sunrise-tangrt1.2.0 | 0.6.0+sunrise3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |
| tsingmicro-tsm260610 | 0.7.0rc2+tsingmicro3.6 | 2.2.0-0.2.2rc2.post2 | ✅ |

spacemit、thead-ppu2.0.0 无 app 镜像，不在表内。

### FlagTree 0.7.0rc2 的两个回归与降版

2.2.0 栈原本统一到 flagtree 0.7.0rc2，两个后端在 0.7.0rc2 上无法工作，
各自回落并已在 FlagTree 报 issue（均带 on-node 最小重现与 0.6.x 对照）：

| 后端 | 0.7.0rc2 上的问题 | issue | 回落至 |
|---|---|---|---|
| enflame-tops1.9.10 | 向 `--convert-gpu-to-gcu` 传 `enable_i64`，tops1.9.10 工具链不认，**所有** kernel 编译失败 | [#1233](https://github.com/flagos-ai/FlagTree/issues/1233) | 0.6.0+enflame3.6 |
| nvidia-cuda13.3 | TLE 在 import 时 dlopen `libflagcx.so`（链 `libcudart.so.12`，CUDA 13 无此库），异常绕过 `has_triton_tle` 的 ImportError 探测，`import flag_gems` 直接失败 | [#1234](https://github.com/flagos-ai/FlagTree/issues/1234) | 0.6.1 |

metax ×2 原本列在此表（#1232，`tl.dot` 在 `BLOCK_SIZE_M=8` 编译期 ICE），
该 issue 已关闭：metax 的 GEMM 配置空间（`mm`/`mm_nn`/`linear`/`addmm`）最小
`BLOCK_M` 是 16，BM=8 只出现在非 `tl.dot` 的归约类算子，端到端 serving 也未复现
（清空 triton cache 与 libentry DB 后 Qwen3.6-27B eager 全用例通过，日志无 BM=8）。
metax ×2 停在 0.6.1 的理由是 F 路径需要的 FlagTree #1052，见
[`backends/metax.md`](backends/metax.md) §2.2。

### 降版后的连带问题：FlagTune cost model

flag_gems `5.4.0rc2.post3` 的 cost model 探测 flagtree 的异常契约，
探测失败时回退到 `(FileNotFoundError, ModelBundleMissingError)`。
0.6.x 的 flagtune 是**旧版而非缺失**：`triton.flagtune` 能 import，
但没有 `runtime/errors.py` / `ModelBundleMissingError`，于是探测成功、
真正抛出的异常类型却不在回退集合内，直接逃逸——表现是**任何走到
cost model 的算子都中止**，vllm serve 在 engine core 初始化即死。

`configs.yaml` 对 cuda13.3、metax ×2、sunrise 设 `env.runtime.USE_FLAGTUNE_COST_MODEL=0`
（sunrise 为预防性：其 0.6.0 同样是旧版 flagtune）。代价是这些后端退回
default tuning——0.6.x 的模型包里本来也没有 FlagGems 算子的模型，
该路径在它们上面不可用。enflame 0.6.0 与 ascend 0.6.0 不含 flagtune，
不受影响；0.7.0rc2 自带完整模块，能自行降级。
