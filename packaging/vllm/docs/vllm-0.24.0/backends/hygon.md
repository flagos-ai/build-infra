# vllm 0.24.0 — hygon dtk26.04

> 本文对应原报告 §12。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。§12.3 为 app 镜像上线后的新 tag 复验，
> 不在原报告内。

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
  （437 行 `setdefault`）解锁验证 —— 显式临时、不可复现（sed 只存在于
  验证容器内，从未进镜像）
- 修复最终以 flagtree 项目发布形式落地：[FlagTree #1020](https://github.com/flagos-ai/FlagTree/pull/1020)
  合入后发布 `0.6.2a1+hcu3.6`，configs.yaml 钉版本（[build-infra #785](https://github.com/flagos-ai/build-infra/pull/785)，
  2026-09-08），runtime 2.1.2 重建即含修复 —— 未走 `packaging/flagtree/hygon`
  本地构建。F 路径在重建后 runtime 上的可用性另经 sglang 0.5.18 hygon
  双编译器 E2E 佐证（[build-infra #792](https://github.com/flagos-ai/build-infra/pull/792)）

### 12.2 T 路径（vendor triton 3.5.1）

`compiler triton` → vendor triton 3.5.1（`/opt/triton`）。serve 到
`Application startup complete`（09:47:40），推理连贯：knowledge
"Paris" ✅、math "42" ✅。算子路由与 F 路径一致（全 `default.flagos`）；
OpManager 10 ops/20 implementations；GPU KV cache 50,320 tokens；
崩溃标记 0。指纹同 F 路径 `vllm-0.24.0-tp2-5c23ce1f`。

### 12.3 vllm-plugin-FL v0.3.0-rc2.post1 tag 验证（2026-09-14）

插件发布 `v0.3.0-rc2.post1`（main head `c9bbcf0`，即其 PR 的 merge commit）后
在新 tag 上重建 app 镜像并双路径复验。此轮起 wheel 版本基跟随 **tag 自身版本**
（`0.3.0rc2.post1`），不再走此前所有 app 镜像共用的 0.2.1 线；重建理由见
`app/vllm/changelogs/vllm0.24.0-hygon-dtk26.04.yaml`。

- 镜像 `harbor.baai.ac.cn/flagos-app/vllm0.24.0-hygon-dtk26.04:2.1.2-0.3.0rc2.post1_gc9bbcf0.d20260914`
- 指纹：vllm `0.24.0+flagos` / vllm-plugin-fl `0.3.0rc2.post1+gc9bbcf0.d20260914`
  / torch `2.9.0+das.opt1.dtk2604` / flagtree `0.6.2a1+hcu3.6`（§12.1 的
  `cluster_dims` 修复即在其中）/ flag_gems 5.3.5 / numpy 1.26.4
- 模型 `/data/models/Qwen/Qwen3-4B`，单卡；serve `--gpu-memory-utilization 0.6
  --enforce-eager --trust-remote-code --max-model-len 2048 --port 8031`

| 路径 | 编译器 | 就绪 | 首请求 | 稳态请求 |
|---|---|---|---|---|
| F | flagtree（triton 3.6.0，`/opt/flagtree`）| 100 s | 24.2 s | 4.0 s |
| T | vendor triton 3.5.1（`/opt/triton`）| 100 s | 28.7 s | 3.8 s |

两条路径均 serve 到 `Application startup complete`，多次补全锚点 "Paris" 稳定
（T 路径另经 5 次重复确认）。**编译器切换不放任推断**：从 `/proc/<pid>/environ`
读回 serve 进程的 `PYTHONPATH`（F `/opt/flagtree`，T `/opt/triton`）作为生效
证据——`compiler` 函数只改当前 shell，用另一 shell 探针会读到默认的 flagtree。
分发（`VLLM_FL_DISPATCH_DEBUG=1`）与 §12.1/§12.2 同形：11 个算子全部
`selected=default.flagos`，`vendor.cuda` 一致被拒，策略取自
`vllm_fl/dispatch/config/hygon.yaml`。

> 单卡固定：`DCU_VISIBLE_DEVICES` **不**收窄设备视图（torch 仍报 8 张卡），
> 需用 `-e HIP_VISIBLE_DEVICES=<n>`（torch 报 `count 1`）。节点为共享机，验证
> 用 HCU1/2，避开他人 CI 占用的 HCU0。
