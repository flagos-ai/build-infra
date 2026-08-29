# verl-FL hygon E2E 验证报告

验证在 hygon25（Hygon BW1000 8× HCU，DTK 26.04）上进行，runtime 镜像
`flagos-runtime-hygon-dtk26.04:2.1.2`，Python 3.10.20，torch
2.9.0+das.opt1.dtk2604。验证周期为 2026-08-27 ~ 2026-08-28。

**缩写:** GRPO = Group Relative Policy Optimization（群体相对策略优化）；
FSDP = Fully Sharded Data Parallel（全分片数据并行）；FL = FlagOS 训练框架
（federated learning 语义下沿用）。

本报告只记录**可复现的技术发现与缺口**（代码级缺陷、版本组合、平台移植性、
工具链限制），不含瞬时错误与一次性环境故障。本报告不记录临时节点、容器、
脚本与运行编号。

## 0. Summary

**结论:** verl-FL 全链路（GRPO 训练：actor/ref 走
FSDPFLEngineWithLMHead，rollout 走 vllm + vllm-plugin-fl，入口
`python3 -m verl.trainer.main_ppo`）首次在 hygon 双编译器路径跑通。
**flagtree 与 vendor triton 两条路径均完成 2 个训练 step + final validation，
exit 0，零 SIGSEGV。**

| 路径 | 状态 | 一句话事实 |
|---|---|---|
| flagtree 0.6.1+hcu3.6 | ✅ 通过 | 2/2 step + validation，exit 0（2026-08-28 17:20 UTC+8） |
| vendor triton 3.5.1 | ✅ 通过 | 2/2 step（07:09）+ validation，exit 0（2026-08-28 21:57 UTC+8） |

**容器内实测包版本:**

| 包 | 版本 |
|---|---|
| verl | 0.7.0+fl.20260828.g03c9b7da（git 安装，非 wheel） |
| vllm | 0.20.2+flagos（build-infra repack） |
| vllm-plugin-fl | 0.2.1 |
| megatron-core | 0.17.1+fl.20260822.g56acf36bacd1 |
| flag_gems | 5.3.4 |
| flagtree | 0.6.1+hcu3.6（/opt/flagtree，triton 3.6.0） |
| vendor triton | 3.5.1（/opt/triton） |
| ray | 2.41.0 |
| flash_attn | 2.8.3+das.opt1.dtk2604.torch290 |
| numpy | 1.26.4（与 configs.yaml stack-wide pin 一致，无冲突） |

**运行所需补丁（BREAK 清单）:** 全链路跑通需要 6 个代码补丁 + 1 个环境变量
（§1）。分布：verl 2 个、vllm-plugin-fl 2 个、torch/_inductor 1 个、
flag_gems 1 个。**六个代码补丁已上提 fork PR（§3）：verl-FL [PR #20]、
vllm-plugin-FL [PR #420]、FlagGems [PR #5841]；torch/_inductor 容错等
FlagTree 重建，ray 环境变量待固化到 verl 启动环境。** isfinite 补丁
（§1.6）仅 triton 路径需要，flagtree 路径不受影响；其余补丁双路径都需要。

**教训清单:**

1. **verl 与 vllm 0.20.2 组合需要 5 处运行期适配**（§1.1~§1.5）——
   verl-FL 上游随 vllm 0.11/0.12 线开发，与 build-infra 认定的 0.20.2+flagos
   存在 API 差异：`execute_method` → `run_method`、kv_cache_config 由对象变
   list、multi-engine 下每引擎独立 config、max_model_len 覆盖、
   `set_current_vllm_config` 上下文缺失。**组合验证是硬工作**，不能只信
   各自单元可用。
2. **vendor hip triton 3.5.1 的 libdevice 缺 finitef/isfinited 符号**
   （§1.6）——verl `optimizer_step` 的 `torch.isfinite(grad_norm)` 触发
   flag_gems isfinite，`_patch_missing_symbols` 借 CUDA `__nv_finitef`
   extern 在 HIP backend 无法 lowering → 编译为 None → `TypeError`。
   flagtree 的 hip libdevice 有真实 `__ocml_isfinite_f32`，不踩。
3. **ray 2.41 teardown SIGSEGV 由环境变量关闭 TaskEventBuffer 修复**
   （§1.7）——`ray.init(enable_task_events=False)` 不是有效 kwarg
   （`RuntimeError`），正确机制是 `RAY_task_events_report_interval_ms=0`。
4. **torch/_inductor 的 make_launcher 对缺 cluster_dims 的 flagtree kernel
   metadata 崩溃**（§1.5）——与 megatron 线 jit_fuser 问题同根因的另一处
   入口，需 num_ctas + cluster_dims 容错。
5. **Adam 惰性初始化 OOM 由配方规避**（§2）——`n_gpus_per_node=2` + FSDP
   FULL_SHARD 把优化器状态分摊到 2 GPU，无需补丁。

## 1. 运行期补丁（BREAK 清单）

全部为验证容器内的代码补丁（非仓库改动）。逐个给出文件、改动与原因。

### 1.1 verl rollout execute_method → run_method

- **文件:** `verl/workers/rollout/vllm_rollout/vllm_rollout.py`
- **改动:**
  ```python
  from vllm.v1.serial_utils import run_method
  return run_method(self.inference_engine.worker, method, args, kwargs)
  ```
  替换 `return self.inference_engine.execute_method(method, *args, **kwargs)`。
- **原因:** vllm 0.20.2 的 worker 方法经 `run_method` 序列化执行，
  `execute_method` 路径不可用。
- **处置:** 已上提 verl-FL [PR #20](https://github.com/flagos-ai/verl-FL/pull/20)（Fixes
  [#19](https://github.com/flagos-ai/verl-FL/issues/19)，`_VLLM_GE_0_20`
  guard 门控，等 merge）。

### 1.2 vllm-plugin-fl kv_cache_config list unwrap + multi-engine 索引

- **文件:** `vllm_fl/worker/worker.py`
- **改动:**
  ```python
  if isinstance(kv_cache_config, list):
      kv_cache_config = kv_cache_config[0] if len(kv_cache_config) == 1 \
          else kv_cache_config[self.rank]
  ```
- **原因:** vllm 0.20.2 executor 传 per-rank 的 kv_cache_config list（stock
  `worker_base.py` 用 `[global_rank]` unwrap）；fork 的 WorkerFL override 遮蔽
  了这段 → `IndexError: list index out of range`。multi-engine
  （n_gpus_per_node=2）下每个 EngineCore 拿到自己的单元素 list（TP=1），须按
  len==1 取 `[0]`，TP>1 才按 engine rank 索引。
- **处置:** 已上提 vllm-plugin-FL [PR #420](https://github.com/flagos-ai/vllm-plugin-FL/pull/420)
  （Closes [#419](https://github.com/flagos-ai/vllm-plugin-FL/issues/419)，base=release/0.2，
  与 §1.3 同一 commit，等 merge）。

### 1.3 vllm-plugin-fl set_current_vllm_config 上下文

- **文件:** `vllm_fl/worker/worker.py`
- **改动:** `initialize_from_config` 的 dispatch 包进
  `with set_current_vllm_config(self.vllm_config):`。
- **原因:** stock WorkerBase 同处有该上下文；fork override 缺失 → 下游
  `get_current_vllm_config()`（kv cache reshape 的
  `get_kv_connector_cache_layout`）失败。
- **处置:** 已上提 vllm-plugin-FL [PR #420](https://github.com/flagos-ai/vllm-plugin-FL/pull/420)
  （与 §1.2 同一 commit，等 merge）。

### 1.4 verl max_model_len 守卫

- **文件:** `verl/workers/rollout/vllm_rollout/vllm_async_server.py`
- **改动:**
  ```python
  if self.config.max_model_len is None:
      self.config.max_model_len = self.model_config.hf_config.max_position_embeddings
  ```
- **原因:** 显式传入 `rollout.max_model_len`（768）时不应被 hf_config 覆盖。
- **处置:** 已上提 verl-FL [PR #20](https://github.com/flagos-ai/verl-FL/pull/20)
  （与 §1.1 同一 commit，等 merge）。

### 1.5 torch/_inductor make_launcher cluster_dims 容错

- **文件:** `torch/_inductor/runtime/triton_heuristics.py`（torch 2.9.0）
- **改动:**
  ```python
  (binary.metadata.num_ctas, *(getattr(binary.metadata, "cluster_dims", None) or (1,)))
  ```
  替换 `*get_first_attr(binary.metadata, "cluster_dims", "clusterDims") or (1,)`。
- **原因:** flagtree 3.6.0 kernel metadata 缺 cluster_dims → make_launcher
  AttributeError；与 megatron 线 jit_fuser 崩溃（同根因）的另一点入口。
- **处置:** 不上提代码；等 FlagTree 侧修复重建 wheel——flagtree 上游
  [PR #1020](https://github.com/flagos-ai/flagtree/pull/1020)（补 cluster_dims
  默认值）已 merge（2026-08-26），0.6.1+hcu3.6 wheel 不含，待 rebuild 后复验。

### 1.6 flag_gems isfinite fallback（triton 路径唯一训练阻塞）

- **文件:** `flag_gems/utils/triton_lang_helper.py`
- **改动:** `_FALLBACK_SYMBOLS` 注册 `"finitef"` / `"isfinited"` → 纯 triton
  fallback：
  ```python
  @triton.jit
  def _fallback_isfinite(x):
      return (x - x) == 0.0
  ```
- **原因:** verl `optimizer_step` 调 `torch.isfinite(grad_norm)` → flag_gems
  isfinite → vendored hip triton 3.5.1 的 libdevice **无** finitef/isfinited
  符号 → `_patch_missing_symbols` 借 CUDA libdevice 的 `__nv_finitef` extern，
  在 HIP backend 无法 lowering → 编译为 None → `TypeError: cannot convert
  None to tensor`。`(x-x)==0.0` 只用 core triton operator，全后端可
  lowering；对任意有限 x 恒为真（x-x 精确 0），对 +-inf/NaN lane 恒为假。
- **处置:** 已上提 FlagGems [PR #5841](https://github.com/flagos-ai/FlagGems/pull/5841)
  （Closes [#5840](https://github.com/flagos-ai/FlagGems/issues/5840)，等 merge）。

### 1.7 ray teardown SIGSEGV（环境变量，非代码补丁）

- **改动:** 启动环境加 `export RAY_task_events_report_interval_ms=0`。
- **原因:** ray 2.41.0 的 `TaskEventBufferImpl::FlushEvents` 在
  `CoreWorker::Disconnect` / `HandleKillActor`（训练 + final validation 之后
  teardown）SIGSEGV，进程挂死。`ray.init(enable_task_events=False)` 无效——
  ray 2.41 不认该 kwarg（`RuntimeError: Unknown keyword argument(s)`）；env
  变量置 0 禁用 TaskEventBuffer 才有效。本次 triton 路径实测触发，flagtree
  路径未触发。
- **处置:** 待固化到 verl 启动文档/脚本（`RAY_task_events_report_interval_ms=0`），
  随 verl app 镜像线落地。

## 2. 复现配方

**模型:** Qwen3-4B（/data/models/Qwen/Qwen3-4B）。**数据:** gsm8k 子集
（8 train / 8 test，parquet）。**入口:**
`python3 -m verl.trainer.main_ppo`，双路径经 runtime 的 `compiler
<flagtree|triton>` 切换。

**关键 env:**

| 变量 | 值 |
|---|---|
| VERL_ENGINE_DEVICE | flagos |
| VERL_PLATFORM | cuda |
| VLLM_PLUGINS | fl |
| VLLM_FL_OOT_ENABLED | 1 |
| TE_FL_PREFER | flagos |
| TE_FL_STRICT | 0 |
| USE_FLAGGEMS | true |
| VLLM_FL_FLAGOS_BLACKLIST | where_scalar_other,where_scalar_self,where_self,where_self_out,pad |
| RAY_task_events_report_interval_ms | 0（§1.7） |
| PYTORCH_CUDA_ALLOC_CONF | expandable_segments:True |

**minimal GRPO 配方**（train_batch_size=4、n=1、num_workers=4）:

| 参数 | 值 | 原因 |
|---|---|---|
| trainer.n_gpus_per_node | 2 | FSDP FULL_SHARD 分摊优化器状态 → 规避 Adam 惰性初始化 OOM |
| +ray_kwargs.ray_init.num_gpus | 8 | 节点 8× HCU |
| actor_rollout_ref.rollout.tensor_model_parallel_size | 1 | 起双 vllm 引擎（多引擎数据并行） |
| data.train_batch_size / max_prompt_length / max_response_length | 4 / 256 / 256 | smoke 规模 |
| actor_rollout_ref.rollout.max_model_len / gpu_memory_utilization | 768 / 0.15 | 小显存占用 |
| actor_rollout_ref.actor.ppo_mini_batch_size | 4 | |
| actor_rollout_ref.actor.fsdp_config.param_offload / optimizer_offload | true / true | |
| actor_rollout_ref.model.enable_gradient_checkpointing | true | |
| trainer.total_epochs / test_freq | 1 / 1 | 单 epoch + final validation |
| trainer.use_legacy_worker_impl | disable | |

**结果信号:** 每条 step 约 115~131 s（其中 generate_sequences 60~93 s），
perf/throughput ≈ 5.2~5.6 tok/s；step 0 验证 reward/acc = 0.125（4 样本中 1
正确），其后 0.0；exit code 经 `|| rc=$?` 捕获（`set -e` 会吞掉 verl 退出
码），以 `VERL_E2E_EXIT_CODE` / `VERL_E2E_RESULT` 输出。

## 3. 跟踪事项

**BREAK 补丁去向（已落地，等 merge）:**

| 补丁 | 去向 | 状态 |
|---|---|---|
| §1.1 / §1.4 verl | verl-FL [PR #20](https://github.com/flagos-ai/verl-FL/pull/20) | 已开，等 merge |
| §1.2 / §1.3 vllm-plugin-fl | vllm-plugin-FL [PR #420](https://github.com/flagos-ai/vllm-plugin-FL/pull/420) | 已开，等 merge |
| §1.6 flag_gems | FlagGems [PR #5841](https://github.com/flagos-ai/FlagGems/pull/5841) | 已开，等 merge |
| §1.5 torch/_inductor | flagtree 侧修复，不上提代码 | 等 wheel rebuild 后复验 |
| §1.7 ray env | 随 verl app 镜像线固化到启动文档/脚本 | 未开始 |

merge 后跟进：各 PR merge 后重走 E2E（相关后端），确认无需 wheel 内补丁；
flagtree rebuild 后复验 §1.5（0.6.1+hcu3.6 后的新 wheel）。

**wheel 化:** verl 目前 git 安装（0.7.0+fl.20260828.g03c9b7da）；app 镜像线
需要 wheel 构建设施（`packaging/verl/builder/` 计划中），且需决定 BREAK
补丁是否先并 fork 再打包（补丁进 wheel 否则镜像内打补丁）。

**vllm 版本线:** 本次验证用 0.20.2+flagos（build-infra 认定版，用户指定）；
verl-FL 默认线 0.11/0.12 未验证。0.20.2 的适配是否回填 verl-FL 默认线由
决策定。

**后续验证范围:** 其余 16 个后端尚未验证（本次仅 hygon）；ascend
（aarch64）的 ray 2.41 wheel 可得性为全后端范围的最大风险（见
`verl-app-image-plan.md`）。
