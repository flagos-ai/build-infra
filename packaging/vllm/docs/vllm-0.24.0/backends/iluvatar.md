# vllm 0.24.0 — iluvatar corex4.5.0

> 本文对应 0.20.2 线 [§2.5 / §2.12](../vllm-0.20.2/backends/iluvatar.md) 的 0.24.0 延续。
> 0.24.0 已验证 corex4.5.0（§14，F/T 双路径）与 corex4.4.0（**F ✅ / T ❌**，见
> [§14.4](#144-corex440-t-路径负结果2026-09-04)；guard #434，wheel `0.2.1+g84a4ca2.d20260902`，
> 记录随 build-infra #688）；0.20.2 线 corex4.4.0 仍为负结果（工具链过旧，见
> 0.20.2 [§2.5](../vllm-0.20.2/backends/iluvatar.md)）。
> 标准流程见 [`playbook.md`](../playbook.md)，决策见 [`decisions.md`](../decisions.md)。
> **TODO（iluvatar 插件 wheel 必须收敛，2026-09-02）：** 本线两 corex 变体现各钉一个 wheel ——
> corex4.5.0 = `0.2.1+g07063fd.d20260828`、corex4.4.0 = `0.2.1+g84a4ca2.d20260902`；
> 0.20.2 线若日后启用 corex4.4.0 还会再涨一个。两 wheel 的代码差仅是 #434
> `_symmetric_memory` guard（torch≥2.8 时为 no-op），后验 head 是超集 → **必须收敛**：
> 以统一 head（≥ #434）重验 corex4.5.0（§14 流程），matrix 两行 `image_tag` 指向同一
> vllm_fl 版本后退役旧 wheel（g07063fd）。禁止「vllm 线 × corex 变体」逐格涨 wheel。
> **corex4.4.0 的 T 路径修复（2026-09-04，[§14.4](#144-corex440-t-路径负结果2026-09-04)）随本次
> 统一 wheel 一并做**：插件在 iluvatar 后端模块作用域强制 `topk_topp_sampler.HAS_TRITON=False`
> （EngineCore 为 spawn 子进程，父进程 patch 不生效，必须模块导入期 patch）。

## 14. iluvatar（COREX 4.5.0）详细记录（2026-08-30）

**平台:** Iluvatar CoreX BI-V150（ix23 节点）　**CoreX:** 4.5.0

**目标:** vllm 0.24.0 (empty) + vllm-plugin-FL 的 **app 镜像**端到端验证，
`harbor.baai.ac.cn/flagos-app/vllm0.24.0-iluvatar-corex4.5.0:2.1.2-0.2.1_g07063fd.d20260828`

**结论：** F/T 双路径均 E2E 通过。0.20.2 线 4.4.0 的乱码负结果由工具链解除
（4.5.0 `torch 2.10.0+corex.4.5.0.20260804`，无需任何补丁/降级/额外 env）——
本次 0.24.0 无阻塞点，一次通过。

### 14.1 App 镜像验证（verify-vllm-backend.sh --app-image）

`--app-image` 模式对比 runtime↔app 关键包矩阵（逐项须一致）→ vllm+vllm_fl 导入 →
真实 serve + completion：

| 检查 | F（flagtree 0.6.1+iluvatar3.6 → 3.6.0） | T（vendor triton 3.2.0） |
|---|---|---|
| BEFORE/AFTER 矩阵 | torch 2.10.0+corex.4.5.0.20260804；triton 无；flag_gems 5.3.5；numpy 1.26.4 —— 逐项一致 | 同左 |
| vllm+vllm_fl 导入 | ✅ `vllm 0.24.0 \| plugin ok` | ✅ 同左 |
| serve 就绪 | ~90s | ~150s |
| completion | ✅ 同文本 | ✅ 同文本 |

> 两路径 completion 同文本：`' Paris. The capital of Germany is Berlin.
> The capital of Italy is Rome.'`（prompt `The capital of France is`，
> max_tokens 16，temp 0）。triton 在默认 python3 视角下无（位于 /opt/triton）。
> 单步安装零泄漏（矩阵不变），容器用后即清。

### 14.2 启动

```bash
docker run -d --network host --device /dev/iluvatar0 \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-iluvatar-corex4.5.0:2.1.2-0.2.1_g07063fd.d20260828
```

默认 CMD 直接 serve（`vllm-serve --model /data/models/Qwen3-4B --port 8031
--gpu-memory-utilization 0.6 --enforce-eager --trust-remote-code
--max-model-len 2048 --dtype bfloat16`，app env 由镜像自带 `VLLM_PLUGINS=fl`）；
显式覆盖模型/参数同 [`playbook.md`](../playbook.md)。

### 14.3 Stack 验证

| 组件 | 版本 |
|---|---|
| vllm | 0.24.0+flagos（cp312 empty wheel，app 单步安装） |
| vllm_fl | 0.2.1+g07063fd.d20260828（vllm-plugin-FL main @ 07063fd7b6ed12c，= image_tag 后缀） |
| torch | 2.10.0+corex.4.5.0.20260804（镜像自带，未降级） |
| flagtree | 0.6.1+iluvatar3.6（F 默认，运行时 3.6.0） |
| triton | T 路径 vendor 3.2.0（/opt/triton） |
| flag_gems | 5.3.5 |
| numpy | 1.26.4（configs.yaml pin） |
| python | 3.12 |

**相关提交：** 镜像构建 + tag 记录（[build-infra #628](https://github.com/flagos-ai/build-infra/pull/628) 记录 image_tag）；F/T 验证记录
（状态矩阵 [build-infra #629](https://github.com/flagos-ai/build-infra/pull/629)）。

### 14.4 corex4.4.0 T 路径负结果（2026-09-04）

**平台:** Iluvatar CoreX（ix15，SDK corex 4.4.0）　**镜像:** 同 §14.3 发布的
`vllm0.24.0-iluvatar-corex4.4.0:2.1.2-0.2.1_g84a4ca2.d20260902`（T = vendor triton 3.1.0，/opt/triton）

**目标:** 补验 corex4.4.0 0.24.0 的 **T（triton）格**（此前只验证了 F 路径默认编译器，
F ✅ 记录于 2026-09-02 / build-infra #688）。

**结论：❌ T 路径不可交付——厂商 corex 编译器存在不可修复缺陷。** 与 0.20.2 线
[§2.5](../vllm-0.20.2/backends/iluvatar.md)（D 前向数值乱码，工具链代差定案）同一定论；
对 4.4.0 SDK 钉死的 vendor corex triton 3.1.0，无法通过插件/镜像层修复。**交付路径 = F
（flagtree），T 不交付。**

**证据链（同一 app 镜像 `g84a4ca2`、同一 ix15 节点、Qwen3-4B，逐层剥离）：**

| 层 | 现象 | 性质 |
|---|---|---|
| 1. 原生 sampler | `apply_top_k_top_p_triton` 三分搜索 `uint32 // int32` → `CompilationError`（复现稳定） | vendor triton 3.1 严格符号检查，**插件可修** |
| 2. 原生 attention | 真实 decode 编译 `triton_unified_attention` → cache_key AST walker 访问 `tl.make_tensor_descriptor` → 先 `AttributeError: no __name__`、补 `__name__` 后 `AssertionError: Function ... is not a Triton function` | triton 3.1 DependencyFinder 严格（3.2 可容忍纯 callable stub，故 corex4.5.0 T ✅）；vllm 0.24 统一 attention kernel 源码恒含 TD 分支，walker 无条件遍历 |
| 3. flag_gems attention（T 下强制 `VLLM_FL_USE_FLAGGEMS_ATTN=1` 绕开 2） | serve 起来、completion 返回，但**输出乱码**（`eld \`vette记者在 ApplicationController...`） | **决定性缺陷**：vendor triton 3.1 对 flag_gems 内核也**误编译**（前向数值错），非插件可修 |

**对照实验（锁死根因 = 厂商编译器，而非镜像/模型/插件）：** 同一容器、同一镜像、
同一模型、同一 flag_gems attention 后端，仅切换编译器：
- **F（默认 flagtree 0.6.1+iluvatar3.6，3.6 前端）** → completion 干净（`' located in Paris, and
  the capital of Germany is located in Berlin...'`，anchor ✅）。
- **T（vendor corex triton 3.1.0）** → 同上配方、同一 flag_gems 内核，输出乱码。

F/T 执行的是**同一批 flag_gems Triton 内核**（`@triton.jit`），仅编译前端不同：F 编译 → 数值对，
T 编译 → 数值错。故乱码必然落在 **vendor corex triton 3.1 编译器本身**（前端解析/代码生成缺陷），
不在 torch、不在 flag_gems、不在插件、不在镜像。0.20.2 §2.5 trap D 在 0.24.0 复证。

**修复边界（为何「不可修复」）：** 插件层能做的只有换内核或绕 Triton——层 1 换 pytorch
sampler、层 2 换 flag_gems attention 均可达 serve，但换到 flag_gems attention 后乱码依旧
（层 3），证明 3.1 下「所有可选 Triton 内核路径」编译执行皆错，无第三个内核可换；而纯 torch
attention 在 vLLM 0.24 无全模型开关、且 BI-V150 上性能数量级不可用。唯一恢复路径 = 厂商升级
corex4.4.0 SDK 工具链（torch 2.7.1 + corex triton 3.1，镜像内不可动；corex4.5.0 的 triton
3.2 + torch 2.10 无此问题，T ✅ 已验证）。**探针 patch（模块作用域 `HAS_TRITON=False`、
stub `__name__`）已实测能让 T 路径 serve 起来但无交付价值，故未合入 vllm-plugin-FL**（避免
改动共享 iluvatar 后端、波及已验证的 F 路径与 corex4.5.0 T 路径）；若厂商升级工具链，二者是
现成恢复路径，届时随 [build-infra #691](https://github.com/flagos-ai/build-infra/pull/691)
统一 wheel 一并评估。
