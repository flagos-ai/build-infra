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
| mthreads musa4.3.6 / 5.2.0 | [mthreads.md](backends/mthreads.md) | 标准流程范例来源；mul 门控 #5130 |
| hygon dtk26.04 | [hygon.md](backends/hygon.md) | 首个复用他机 wheel 后端；torch↔numpy ABI |
| iluvatar corex4.4.0 / 4.5.0 | [iluvatar.md](backends/iluvatar.md) | 4.4.0 乱码（工具链过旧）；4.5.0 ✅ F/T 双路径 E2E |
| enflame tops1.9.10 / 1.10.6 | [enflame.md](backends/enflame.md) | GCU300 ✅ E2E；vLLM 原生 FLASH_ATTN |
| cambricon neuware4.7.2 | [cambricon.md](backends/cambricon.md) | §2.7 MLU590 主记录 |
| ascend cann9.0.0 | [ascend.md](backends/ascend.md) | 910B4 aarch64 cp311；fork-SHA 溯源表 |
| sunrise tangrt1.2.0 | [sunrise.md](backends/sunrise.md) | FlagTree decode 挂死 → 已修复（PR 978）|
| kunlunxin xre5.37.1 | [kunlunxin.md](backends/kunlunxin.md) | P800 XPU；解码乱码 PR #400 + 假死 KL3 |
| cambricon neuware4.4.3 | [cambricon.md](backends/cambricon.md) | §2.11，T-only 兼容 shim ×5 |
