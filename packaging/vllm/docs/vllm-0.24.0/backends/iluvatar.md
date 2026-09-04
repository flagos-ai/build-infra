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

**结果：❌ T 路径 engine init 崩（复现稳定）**。`compiler triton` + serve Qwen3-4B
（`--enforce-eager --gpu-memory-utilization 0.6`，同 §14.1 配方）在
`profile_run → _dummy_sampler_run → topk_topp_sampler → apply_top_k_top_p` 处崩：

```
triton.compiler.errors.CompilationError: at 107:24:
TypeError('Cannot use /, #, or % with triton.language.uint32 and triton.language.int32
because they have different signedness; ...')
```

即 vllm 0.24.0 上游 `topk_topp_triton.py` 的三分搜索内核
`(num_outliers + BLOCK_SIZE_TRUNC - 1) // BLOCK_SIZE_TRUNC`（uint32 // int32）在
**vendor triton 3.1.0**（corex fork，严格符号检查）下不可编译——与 0.20.2 线
[§2.5 阻塞点 B](../vllm-0.20.2/backends/iluvatar.md) 同类（工具链代差）。F 路径用
flagtree 0.6.1+iluvatar3.6（3.6 基座前端）无此问题，故 F ✅。

**插件现有 iluvatar sampler patch 不覆盖此路径：** `patch_sampler_compile_for_iluvatar`
unwrap 的是 `compiled_random_sample`（forward_cpu 无 generator 分支用），而崩溃点在
`apply_top_k_top_p`（forward_native 恒走）。且 EngineCore 是 **spawn** 子进程，父进程
运行时 patch（`topk_topp_sampler.HAS_TRITON=False` 等）不随 fork 生效——实测父进程
patch 后 EngineCore 仍以 HAS_TRITON=True 编译该内核。

**修复方向（未实施，待插件）：** 在 vllm-plugin-FL iluvatar 后端模块**导入期**（模块作用域）
强制 pytorch sampler 回退（`topk_topp_sampler.HAS_TRITON = False`，或 wrap
`apply_top_k_top_p` → `apply_top_k_top_p_pytorch`），使 spawn 的 EngineCore 同样生效。
随 wheel 收敛 TODO（[build-infra #691](https://github.com/flagos-ai/build-infra/pull/691)，
统一 head ≥ #434）一并做；合入后重建 wheel + app 镜像 → 重验 T 格翻 ✅。
**交付现状：corex4.4.0 0.24.0 交付路径 = F（flagtree），T 不交付。**
