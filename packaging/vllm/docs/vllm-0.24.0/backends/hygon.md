# vllm 0.24.0 — hygon dtk26.04

> 本文对应原报告 §12。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 12. hygon（DTK 26.04）详细记录（2026-08-20）

hygon 是 python 3.10（cp310 empty wheel，同 [sunrise §11.1](sunrise.md) 的构建前置），
device_type 仍为 `"cuda"`（DCU 以 CUDA 形态暴露）。E2E 于 2026-08-20 完成，
**双编译器路径全 ✅**：

- 镜像 `flagos-runtime-hygon-dtk26.04:2.1.2`
- 模型 `/data/Sky-T1-32B-Preview-FlagOS`（Sky-T1 32B，Qwen2 架构；矩阵
  "Qwen3-4B"约定在此单元格不适用，同 [mthreads §8](mthreads.md) /
  [sunrise §11.3](sunrise.md) 先例）
- serve：`--enforce-eager --trust-remote-code --max-model-len 2048
  --dtype float16 --gpu-memory-utilization 0.6 --tensor-parallel-size 2
  --port 8031`；env `VLLM_PLUGINS=fl VLLM_FL_DISPATCH_DEBUG=1`
- 版本指纹：vllm `0.24.0+flagos`（cp310 empty wheel，单步安装）；
  vllm-plugin-fl `0.2.0+g754c8fe23`；torch 2.9.0+das.opt1.dtk2604 /
  flag_gems 5.3.4 / numpy 1.26.4 / python 3.10
- 编译器：flagtree 0.6.1+hcu3.6（`triton.__version__` = 3.6.0，默认
  `/opt/flagtree`）+ vendor triton 3.5.1（`/opt/triton`），`compiler`
  函数切换
- 指纹：system_fingerprint `vllm-0.24.0-tp2-5c23ce1f`（tp2 后缀 =
  tensor-parallel-size 2；两条编译器路径同一 wheel/plugin，指纹一致）

### 12.1 F 路径（flagtree 0.6.1+hcu3.6）

serve 到 `Application startup complete`（09:27:04），推理连贯：
knowledge `The capital of France is` → " Paris. ..." ✅、math
`What is 6 times 7?` → " 42. ..." ✅。算子路由：`attention_backend`/
`rms_norm`/`rotary_embedding`/`silu_and_mul` 全部 `default.flagos`
（kind=flagos，vendor=None）；OpManager 10 ops/20 implementations；
GPU KV cache 50,720 tokens；崩溃标记 0。

**前置排障：`cluster_dims` AttributeError（FlagTree 根因）**—— 首次
serve 在 KV-cache profiling warmup 阶段崩 `AttributeError`（torch
2.9.0 `make_launcher` 无条件读 `kernel.metadata.cluster_dims`），根因
= flagtree `CompiledKernel.__init__` 从 metadata JSON 构造
`KernelMetadata` namedtuple 时，hcu/mthreads 后端（无 cluster-launch
支持）不产出 `cluster_dims` key，而 vendor triton 3.5.1 与 flagtree
iluvatar overlay 都用 `(1,1,1)` 兜底。修复 = 一行
`metadata.setdefault("cluster_dims", (1, 1, 1))`：

- 上游：FlagTree [PR #1020](https://github.com/flagos-ai/FlagTree/pull/1020)（`fix(compiler): default cluster_dims=(1,1,1)
  for backends that omit it`，分支 fix/cluster-dims-default，
  2026-08-20 提交）
- 临时绕过：就地 sed 到 `/opt/flagtree/triton/compiler/compiler.py`
  （437 行 `setdefault`）解锁验证 —— 显式临时、不可复现；可复现修复
  = PR 合入后重建 flagtree hygon wheel（`packaging/flagtree/hygon`，
  待建，同 [sunrise §11.5](sunrise.md) 模式）

### 12.2 T 路径（vendor triton 3.5.1）

`compiler triton` → vendor triton 3.5.1（`/opt/triton`）。serve 到
`Application startup complete`（09:47:40），推理连贯：knowledge
"Paris" ✅、math "42" ✅。算子路由与 F 路径一致（全 `default.flagos`）；
OpManager 10 ops/20 implementations；GPU KV cache 50,320 tokens；
崩溃标记 0。指纹同 F 路径 `vllm-0.24.0-tp2-5c23ce1f`。
