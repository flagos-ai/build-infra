# vllm 0.24.0 — ascend cann9.0.0 / cann8.5.0

> 本文对应原报告 §10。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 10. ascend（CANN 9.0.0）详细记录

- 镜像：`flagos-runtime-ascend-cann9.0.0:2.1.2`（aarch64，CANN 9.0.0，
  驱动 26.0.rc1，设备 Ascend910B4）
- venv：`/flagos`（cpython-3.11）
- vllm：`0.24.0+flagos`（厂商索引单步安装，命中 `+flagos` wheel）
- 插件：`feat/ascend-v024`（PR #387）editable install，
  `vllm-plugin-fl==0.0.0+g09cd07358`（`--no-build-isolation`）
- 编译器：flagtree 0.6.1+ascend3.5（默认）；侧装 `/opt/triton` =
  triton 3.5.0 + triton_ascend 3.2.1（triton 路径 E2E 见 §10.4）
- torch 2.10.0+cpu / torch_npu 2.10.0 / flag_gems 5.3.4
- 模型：`/data/models/Qwen/Qwen3-4B`；端口 8031

### 10.1 移植内容（PR #387）

0.24.0 升级（#274）从未触碰 ascend 目录：`get_name()` 仍返回
`"ASCEND_FL"`，而 0.24.0 的 `AttentionBackendEnum` 无此成员（扩展只能走
`CUSTOM` 槽位）→ 任何 ascend 启动都崩在
`vllm/model_executor/layers/attention/attention.py:401`
（`ValueError: Unknown attention backend: 'ASCEND_FL'`）。PR #387 恢复
0.24.0 基线上的可用 ascend 后端，三块内容：

1. **PR #307 移植**（`1326a33`，13 文件 +1786/−194）：CUSTOM 后端注册、
   `get_supported_kernel_block_sizes → [128]`、`supports_update_block_table`、
   NPU 平台配置、FLA/GDN ops、fused_moe kernels、MMEncoder attention。
2. **PR #361 黑名单**（`baeafde`，ascend.yaml +9）：`lift_fresh` /
   `lift_fresh_copy` / `_to_copy`（coreDim=0 标量张量初始化崩溃规避）。
3. **0.24.0 特有 worker.py 修复**（`09cd073`）：0.24.0 把 profile 派生计算
   （torch_peak_increase、kv-cache 预算、cudagraph 估计）移到 profiling
   with 块外的函数级；cherry-pick 后 NPU 分支落入 profiling 块
   （`NameError` + 覆盖 NPU kv-cache 预算）。修法：整块移回 `else`、
   `cudagraph_memory_estimate = 0` 默认、NPU 分支跳过 profile_run。

0.20.2 基线的全量测试结果（27B/35B-A3B TP2，文本/图像/并发 18 项全绿）
与 0.24.0 定制详情见 PR #387 正文。

### 10.2 serve + 推理（Qwen3-4B，TP1）

serve 命令（NPU 绑定 + davinci 设备节点，容器挂载模型只读）：

```bash
/flagos/bin/python -m vllm.entrypoints.openai.api_server \
  --model /data/models/Qwen/Qwen3-4B --port 8031 \
  --gpu-memory-utilization 0.6 --enforce-eager \
  --trust-remote-code --max-model-len 2048 --dtype bfloat16
```

- 启动链：`Application startup complete` → 插件 OpManager 逐 op 解析：
  `Op 'rms_norm' using 'vendor.ascend'`、`Op 'rotary_embedding' using
  'vendor.ascend'`、`Op 'silu_and_mul' using 'default.flagos'` —— ascend
  自有实现覆盖部分算子，其余回退默认实现（同 [mthreads](mthreads.md)
  模式）。
- 推理：两条 completions 均连贯（指纹 `vllm-0.24.0-563743c8`）：
  - knowledge：`The capital of France is` → " Paris. The capital of
    Germany is Berlin. ..." ✅
  - math：`What is 7 times 8? Answer:` → " 56. What is 7 times 9?
    Answer: 63. ..." ✅
- **性能注记**：NPU JIT 冷启动首 token 分钟级（首个请求约 7 分钟，其中
  大部分是首个 kernel 的编译/加载）；稳态吞吐约 0.1-0.2 token/s。以功能
  验证为目的，性能不做横向比较。
- **非致命警告**：flag_gems `index_select.py:45` UserWarning（张量逻辑
  `and`/`or`，弃用语义）—— 上游 flag_gems 5.3.4 问题，不影响正确性，
  列入遗留（[§15](../index.md)）。
- **GDN/hybrid 模型（Qwen3-Next）0.24.0 暂不支持**：0.24.0 把
  `mamba/gdn_linear_attn.py` 重构为 `mamba/gdn/` 包，patch.py 的 GDN
  补丁目标符号失效（try/except 静默 no-op）。plain-attention 模型
  （Qwen3、Qwen2、Llama…）不受影响；重构 GDN 补丁为后续工作。

### 10.3 cann8.5.0 双编译器验证

- 镜像：`flagos-runtime-ascend-cann8.5.0:2.1.2`（aarch64，CANN 8.5.0，
  Ascend910B4）
- 版本：flagtree 0.6.0+ascend3.2（默认）；`compiler triton` →
  `/opt/triton` = triton 3.2.0 + triton_ascend 3.2.0；torch 2.9.0+cpu /
  torch_npu 2.9.0 / flag_gems 5.3.4；vllm `0.24.0+flagos`（cp311
  aarch64 empty wheel）
- 插件：`feat/ascend-v024`（PR #387 分支）editable install，源码 commit
  `cf8998c`（容器内 git-less 副本，`vllm-plugin-fl==0.0.0` 无 commit 后缀）
- 模型：`/data/models/Qwen/Qwen3-4B`；serve 参数同 §10.2，端口
  8032（triton）/ 8031（flagtree）

**双编译器 E2E 全绿**（2026-08-18，commit `cf8998c` 配置，两请求均
HTTP 200、输出与 CANN 9.0.0 §10.2 一致）：

| 编译器 | knowledge | math | 崩溃标记 |
|---|---|---|---|
| triton_ascend 3.2.0 | 7.75s 连贯 | 3.90s 连贯 | 0 |
| flagtree 0.6.0+ascend3.2 | 10.57s 连贯 | 5.54s 连贯 | 0 |

算子路由同 §10.2：`attention_backend`/`rms_norm`/`rotary_embedding` →
`vendor.ascend`，`silu_and_mul` → `default.flagos`。

**关键修复：`linear` 黑名单（`cf8998c`）—— triton 路径 decode 挂死**

- 现象：flagtree 路径正常；`compiler triton` 后 decode 循环挂死，
  EngineCore 停在 `get_current_stream`，AICore 钉在 ~111%。
- 根因：flag_gems `linear`（aten::linear，`flag_gems/ops/linear.py`）在
  triton_ascend 3.2.0 下对 decode（M=1）形状死转。SIGUSR1 栈转储定位：
  main 线程 → `linear` → triton runner（`libentry.py` run）→
  `driver.py:219 get_current_stream` → `_npu_getCurrentRawStream`。
  flagtree 0.6.0+ascend3.2 编译同一 kernel 正常 → 编译器侧差异。
- 修法：`ascend.yaml` `flagos_blacklist` 增加 `linear`（mm/addmm 已
  在列表），回退 `torch_npu.linear`（数值等价）。加后 triton 路径两次
  E2E 全绿；容器 yaml 与仓库 `cf8998c` 逐字节一致（YAML_IDENTICAL）。
- 其余 cann8.5.0 triton 黑名单（wrapper 函数名，非 op 名）：`pow`
  （`dd5b76e`）、`cumsum`（`679085e`，get_num_sms None）、
  `repeat_interleave`（`36ec4e4`，MLIR stride 崩溃）。

**被证伪的尝试：silu_and_mul 重排**

一度怀疑挂死与 `silu_and_mul` 路由顺序相关，容器 yaml 临时改
`[vendor, flagos, reference]` 验证；还原提交态 `[flagos, vendor,
reference]` 后再跑仍全绿 → 重排非必要，仓库未改（容器最终与仓库一致）。

**良性警告**（Qwen3-4B 无 GDN 层，不影响正确性）

- GDN patch 静默 no-op（`No module named
  vllm.model_executor.layers.mamba.gdn_linear_attn`，0.24.0 重构为
  `mamba/gdn/` 包所致，同 §10.2）；
- torchvision 回退（PR #386 guard 按设计工作）；
- `TritonToStructured: Pointer analysis is not supported`（triton 侧）；
- shutdown 期 `resource_tracker` 泄漏 semaphore 提示（UserWarning）；
- empty wheel `Failed to import from vllm._C`（预期）。

**指纹**：`vllm==0.24.0+flagos` + 插件 commit `cf8998c`。注：banner 仅
`version 0.24.0`（无 hex 后缀），日志无可提取的 `vllm-0.24.0-<hash>` 串；
§10.2 的 `vllm-0.24.0-563743c8` 为当时会话 run 标识，本小节以 wheel
版本 + 插件 commit 为准。

### 10.4 cann9.0.0 triton 路径 E2E（2026-08-18）

补上 §10.2 缺失的 triton 侧验证（cann9.0.0 此前未单独 serve triton
路径；cann8.5.0 的 triton 侧见 §10.3）：

- 镜像：`flagos-runtime-ascend-cann9.0.0:2.1.2` 重建（PR #428
  triton overlay unzip 修复后）
- 版本指纹：vllm `0.24.0+flagos`（cp311 aarch64 empty wheel）；
  torch 2.10.0+cpu / torch_npu 2.10.0 / flag_gems 5.3.4；
  `compiler triton` → `/opt/triton` = triton 3.5.0（dist 名）+
  triton_ascend 3.2.1 overlay（`triton.__version__` = 3.2.0，
  backends `['ascend']`）—— 与 cann8.5.0 的 3.2.0 树为同源 overlay
- 插件：PR #387 分支 `cf8998c`（容器内 git-less 副本，
  `vllm-plugin-fl==0.0.0`），`--no-build-isolation` editable install
- serve：参数同 §10.2，端口 8033，`compiler triton` +
  `VLLM_FL_DISPATCH_DEBUG=1`
- 启动：`Application startup complete`；算子路由同 §10.2：
  `attention_backend`/`rms_norm`/`rotary_embedding` →
  `vendor.ascend`，`silu_and_mul` → `default.flagos`
- 推理：两条 completions 均连贯（指纹 `vllm-0.24.0-0535d777`）：
  - knowledge：`The capital of France is` → " Paris. The capital of
    Germany is Berlin. ..." ✅
  - math：`What is 7 times 8? Answer:` → " 56. What is 7 times 9? ..." ✅
- 崩溃标记：0（无 Traceback / CUDA error / segfault；serve 进程存活）
- **FlagGems 精度测试（triton 路径附加证明，2026-08-18）**：停 serve 后在同一
  容器内跑 v5.3.4 测试树（与 wheel 精确匹配，pytest 9.0.3），
  `compiler triton` + `--quick --record json`，9 个代表性 stable 算子
  （`add`/`mul`/`abs`/`sum`/`amax`/`softmax`/`add_rms_norm`/`mm`/`bmm`，
  覆盖 pointwise / reduce / softmax / norm / GEMM kernel 类别）：
  **66 passed / 9 skipped / 0 failed**（188s）。skipped 均在预期内
  （8 个 complex dtype 变体——OOT runtime 无 complex 支持；1 个 mm TMA
  compile-error 负向测试）。另有 2 个 collection errors 与本次无关：
  `test_cholesky_solve.py` import 不存在的 backend 模块、
  `test_multinomial.py` 缺 scipy（OOT runtime 不装）。
- **结论**：cann9.0.0 双编译器路径全绿，与 cann8.5.0（§10.3）一致；
  cann8.5.0 的 `linear`/`pow`/`cumsum`/`repeat_interleave` 黑名单
  （`cf8998c`）在 triton_ascend 3.2.1 下同样成立（E2E 未触发挂死）；
  triton 编译器在 kernel 层亦验证可用（FlagGems 精度 66/66）。

### 10.5 app 镜像 serve E2E（2026-08-18）

§10.1–10.4 均为 runtime 镜像 + editable 插件；本节验证**交付形态**：
app 镜像（wheel 单步安装线 + `vllm-serve` launcher）在 NPU 上的
serve + 推理，即 `app/vllm/` 全流程的端到端证明。

- 镜像：`harbor.baai.ac.cn/flagos-app/vllm0.24.0-ascend-cann9.0.0:2.1.2-0.2.0_gcf8998c.d20260818`
  （构建 run 32146899749；2026-08-19 按新命名 re-tag 至 flagos-app，
  flagos-dev 下旧 `vllm-ascend-cann9.0.0:2.1.2` tag 保留）
- 版本指纹：vllm `0.24.0+flagos`（cp311 aarch64 empty wheel，
  单步安装）；vllm-plugin-fl `0.2.0+gcf8998c.d20260818`（vendor PyPI
  wheel，非 editable —— setuptools-scm 编码同 §10.4 的 `cf8998c`
  commit，同一 PR #387 代码）；torch 2.10.0+cpu / torch_npu 2.10.0 /
  flag_gems 5.3.4；torchvision/torchaudio 未安装（OOT 矩阵保持）；
  编译器 = 默认 flagtree 0.6.1+ascend3.5（`VLLM_PLUGINS=fl` 烘焙）
- 启动：`vllm-serve`（`/etc/bash_env.sh` 源入 vendor env →
  `exec api_server`），`docker run` 裸 `--device` flags，端口 8031：
  `--model /models/Qwen3-4B --gpu-memory-utilization 0.6
  --enforce-eager --trust-remote-code --max-model-len 2048
  --dtype bfloat16`（默认 CMD 以 `/data/models/Qwen/Qwen3-4B` 为参考，
  本次挂载路径不同故覆盖）
- 启动：`Application startup complete`；`Block size is set to 128`
  （prefix cache / chunked prefill 补丁生效）、
  `HybridAttentionMambaModelConfig` 补丁生效、`Custom fusions:
  norm_quant, act_quant`；算子路由同 §10.2/10.4
- 推理：两条 completions 均连贯（指纹 `vllm-0.24.0-0535d777`，与
  §10.4 同一 wheel）：
  - knowledge：`The capital of France is` → " Paris. The capital of
    Germany is Berlin. ..." ✅
  - math：`What is 7 times 8? Answer:` → " 56. What is 7 times 9? ..." ✅
- 崩溃标记：0（无 Traceback / 无挂死；容器存活，端口 8031 监听）
- **排障记录（device_count=0 根因）**：本镜像首次 serve 崩在
  `init_device` 的 `AssertionError: DP adjusted local rank 0 is out of
  bounds. Device count: 0`。逐层排查：新鲜 app 容器与新鲜 runtime 容器
  均 `torch_npu.npu.device_count()=0`，而宿主 `npu-smi` 显示 8 卡全
  OK → 排除 app 镜像回归，锁定节点侧。根因 = **§10.4 遗留容器
  持有 `/dev/davinci0`**（其 python 进程已
  defunct，但 NPU 句柄未释放，容器外 open 报 `EBUSY`；容器内
  torch_npu 探测到 0 设备）。`docker rm -f` 该遗留容器后，同一 launch
  立即 `device_count=1`，serve 全绿。教训：ascend 节点上
  "容器已 Exited/僵尸但设备仍被占用" 会让后续容器静默看到 0 设备 ——
  serve 前先 `npu-smi info -t proc-mem` 确认设备空闲（本次宿主侧
  proc-mem 显示 "No process in device" 与真实占用不一致，须以
  `docker ps -a` + 设备 open 实测为准）。

### 10.6 app 镜像 serve E2E（cann8.5.0，2026-08-24）

cann8.5.0 的 app 镜像交付形态验证（§10.3 为 runtime 镜像 +
editable 插件，本节为 wheel 单步安装线 + `vllm-serve` launcher，即
`app/vllm/` 全流程端到端证明）。

- 镜像：`harbor.baai.ac.cn/flagos-app/vllm0.24.0-ascend-cann8.5.0:2.1.2-0.2.0_gcf8998c.d20260818`
- 版本指纹：vllm `0.24.0+flagos`（cp311 aarch64 empty wheel 单步安装）；
  vllm-plugin-fl `0.2.0+gcf8998c.d20260818`（vendor PyPI wheel，非
  editable）；torch 2.9.0+cpu / torch_npu 2.9.0 / flag_gems 5.3.4；
  编译器 = flagtree 0.6.0+ascend3.2（默认，`VLLM_PLUGINS=fl` 烘焙）+
  triton 3.2.0（triton_ascend 3.2.0），`compiler` 函数切换。注：与
  cann9.0.0 app 镜像（§10.5）的 flagtree 0.6.1+ascend3.5 不同。
- 启动：`vllm-serve`（`/etc/bash_env.sh` 源入 vendor env → `exec
  api_server`），`docker run` 裸 `--device` flags，端口 8031（F，
  davinci0，默认 flagtree）/ 8032（T，davinci1，`compiler triton`）：
  `--model /models/Qwen3-4B --gpu-memory-utilization 0.6
  --enforce-eager --trust-remote-code --max-model-len 2048
  --dtype bfloat16`（默认 CMD 以 `/data/models/Qwen/Qwen3-4B` 为参考，
  本次挂载 `/models/Qwen3-4B`，须显式覆盖 `--model`，否则
  `Repo id must be in the form ...` 直接退出）
- 启动：`Application startup complete`；`Block size is set to 128`、
  `Custom fusions: norm_quant, act_quant`；算子路由同 §10.3：
  `attention_backend`/`rms_norm`/`rotary_embedding` → `vendor.ascend`，
  `silu_and_mul` → `default.flagos`，`linear_backend='auto'`。指纹
  `vllm-0.24.0-0568564d`（两路径一致；§10.5 为
  `vllm-0.24.0-0535d777`，插件 wheel 版本串相同、指纹 hash 不同）

**双路径结果：F（flagtree）/ T（triton）均连贯 ✅**

| 编译器 | knowledge | math | 崩溃标记 |
|---|---|---|---|
| triton 3.2.0 | 连贯 ✅ | 连贯 ✅ | 0 |
| flagtree 0.6.0+ascend3.2 | 连贯 ✅ | 连贯 ✅ | 0 |

- T 路径：knowledge `The capital of France is` → " Paris. The capital
  of Germany is Berlin. ..."；math `What is 7 times 8? Answer:` →
  " 56. What is 7 times 9? Answer: 63. ..."。
- F 路径：冷启动（`Application startup complete` 后立即）连续 10 发、
  预热后连续 12 发，knowledge/math 均连贯，共 22/22 无乱码。

**F 路径瞬态乱码（未复现，记观察）**

- 现象：首轮验证会话中，F 路径曾连续 4 次产出降质输出 —— knowledge 3
  次纯 `!` 重复（`max_tokens=32` → 32 个 `!`、`max_tokens=16` → 16 个
  `!`，temperature=0），math 1 次半连贯但错（"7 times 8 is 5!"）。单
  token 重复填充至 max_tokens 长度，是 decode 循环产出单一重复 token
  的数值/分发退化，非 JSON 解析伪影。
- 复测：同一镜像冷启动重测（本节）22/22 连贯，乱码未复现 → 判定为
  间歇性（非确定性）flagtree 0.6.0+ascend3.2 decode 异常，暂未定位。
- 疑点：启动日志 `flag_gems libentry` 警告 "active Triton backend
  does not provide a replay benchmarker; falling back to event timing"
  —— flagtree 的 replay benchmarker 回退到 event timing，可能在特定
  状态下选到次优/错误 kernel config，或与首轮会话的设备状态相关。
- **处置**：cann8.5.0 交付路径 = 默认 flagtree（T 路径 triton 3.2.0
  已同步验证为绿，作为 fallback）。F 路径乱码列为 watch 项，若再现
  需切 `compiler triton` 并定位 flagtree 0.6.0+ascend3.2 的
  benchmarker/数值问题。

---
