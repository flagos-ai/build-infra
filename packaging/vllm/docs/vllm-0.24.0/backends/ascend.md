# vllm 0.24.0 — ascend cann9.0.0 / cann8.5.0

> 本文对应原报告 §10。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 10. ascend（CANN 9.0.0）详细记录

- 镜像：`flagos-runtime-ascend-cann9.0.0:2.1.2`（aarch64，CANN 9.0.0，
  驱动 26.0.rc1，设备 Ascend910B4）
- venv：`/flagos`（cpython-3.11）
- vllm：`0.24.0+flagos`（厂商索引单步安装，命中 `+flagos` wheel）
- 插件：`feat/ascend-v024`（[VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387)）editable install，
  `vllm-plugin-fl==0.0.0+g09cd07358`（`--no-build-isolation`）
- 编译器：flagtree 0.6.1+ascend3.5（默认）；侧装 `/opt/triton` =
  triton 3.5.0 + triton_ascend 3.2.1（triton 路径 E2E 见 §10.4）
- torch 2.10.0+cpu / torch_npu 2.10.0 / flag_gems 5.3.4
- 模型：`/data/models/Qwen/Qwen3-4B`；端口 8031

### 10.1 移植内容（[VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387)）

0.24.0 升级（[VPF #274](https://github.com/flagos-ai/vllm-plugin-FL/pull/274)）从未触碰 ascend 目录：`get_name()` 仍返回
`"ASCEND_FL"`，而 0.24.0 的 `AttentionBackendEnum` 无此成员（扩展只能走
`CUSTOM` 槽位）→ 任何 ascend 启动都崩在
`vllm/model_executor/layers/attention/attention.py:401`
（`ValueError: Unknown attention backend: 'ASCEND_FL'`）。[VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387) 恢复
0.24.0 基线上的可用 ascend 后端，三块内容：

1. **[VPF #307](https://github.com/flagos-ai/vllm-plugin-FL/pull/307) 移植**（`1326a33`，13 文件 +1786/−194）：CUSTOM 后端注册、
   `get_supported_kernel_block_sizes → [128]`、`supports_update_block_table`、
   NPU 平台配置、FLA/GDN ops、fused_moe kernels、MMEncoder attention。
2. **[VPF #361](https://github.com/flagos-ai/vllm-plugin-FL/pull/361) 黑名单**（`baeafde`，ascend.yaml +9）：`lift_fresh` /
   `lift_fresh_copy` / `_to_copy`（coreDim=0 标量张量初始化崩溃规避）。
3. **0.24.0 特有 worker.py 修复**（`09cd073`）：0.24.0 把 profile 派生计算
   （torch_peak_increase、kv-cache 预算、cudagraph 估计）移到 profiling
   with 块外的函数级；cherry-pick 后 NPU 分支落入 profiling 块
   （`NameError` + 覆盖 NPU kv-cache 预算）。修法：整块移回 `else`、
   `cudagraph_memory_estimate = 0` 默认、NPU 分支跳过 profile_run。

0.20.2 基线的全量测试结果（27B/35B-A3B TP2，文本/图像/并发 18 项全绿）
与 0.24.0 定制详情见 [VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387) 正文。

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
- 插件：`feat/ascend-v024`（[VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387) 分支）editable install，源码 commit
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
- torchvision 回退（[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386) guard 按设计工作）；
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

- 镜像：`flagos-runtime-ascend-cann9.0.0:2.1.2` 重建（[build-infra #428](https://github.com/flagos-ai/build-infra/pull/428)
  triton overlay unzip 修复后）
- 版本指纹：vllm `0.24.0+flagos`（cp311 aarch64 empty wheel）；
  torch 2.10.0+cpu / torch_npu 2.10.0 / flag_gems 5.3.4；
  `compiler triton` → `/opt/triton` = triton 3.5.0（dist 名）+
  triton_ascend 3.2.1 overlay（`triton.__version__` = 3.2.0，
  backends `['ascend']`）—— 与 cann8.5.0 的 3.2.0 树为同源 overlay
- 插件：[VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387) 分支 `cf8998c`（容器内 git-less 副本，
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
  commit，同一 [VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387) 代码）；torch 2.10.0+cpu / torch_npu 2.10.0 /
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

### 10.7 app 镜像 serve E2E（910C 双后端，2026-09-11）

910C 是独立后端：`ascend-cann8.5.0-910c`（hw114）与 `ascend-cann9.0.0-910c`（hw115）。
两者 image tag 与各自非 910C 后端只差 `-910c` 后缀，但彼此的 CANN / flagtree / torch
均不同（见下表），**且结论与非 910C 后端也不同，三节不得互相套用**。同版本 app 的
910C 双后端实测：

| 后端 | F（flagtree） | T（vendor triton 3.2.0） |
|---|---|---|
| cann9.0.0-910c | 连贯 ✅ | 连贯 ✅ |
| cann8.5.0-910c | 连贯 ✅ | **退化 ❌** |

镜像 `harbor.baai.ac.cn/flagos-app/vllm0.24.0-{backend}:2.1.2-0.2.0_gcf8998c.d20260818`
（两端同 tag，指纹不同）：

| 后端 | vllm-plugin-fl | torch / torch_npu | flagtree | flag_gems |
|---|---|---|---|---|
| cann8.5.0-910c | `0.2.0+gcf8998c.d20260818` | 2.9.0+cpu / 2.9.0 | 0.6.0+ascend3.2 | 5.3.5 |
| cann9.0.0-910c | `0.2.0+gcf8998c.d20260818` | 2.10.0+cpu / 2.10.0 | 0.6.1+ascend3.5 | 5.3.5 |

（§10.6 的非 910C cann8.5.0 线为 flag_gems 5.3.4，与本节的 5.3.5 是两条线的真实差异。）
`/opt/flagtree` 与 `/opt/triton` 的 `triton.__version__` **均自报 3.2.0**，故每轮须按编译器
分设 `TRITON_CACHE_DIR`，否则缓存串台。

serve 参数（两后端一致）：Qwen3-4B bf16（`--dtype` 取 auto）、TP1、端口 8031、
`VLLM_PLUGINS=fl`、`VLLM_FL_DISPATCH_DEBUG=1`、`--enforce-eager --trust-remote-code
--max-model-len 2048 --gpu-memory-utilization 0.6`。

**cann8.5.0-910c / T 的症状**：每次冷启动都把 `!` 重复填充到 `max_tokens`（HTTP 200、
`finish_reason='length'`、temperature=0）。CI verify 一次命中即此症状：
`completion failed semantic check: expected 'Paris' in text '!!!!!!!!!!!!!!!!'`
（同轮 `serve ready after ~130s`、`triton (active) - 3.2.0`）。5 次**完整冷启动**
（每次新容器 / 新设备 / 新 serve 进程，与 CI 同构）**5/5 FAIL**，输出逐次一致
→ **确定性失败，非间歇**。

**已排除项（均为本机一手实测）**

1. **不是 dispatch 路由差异。** 四份 serve 日志的路由表两两比对：F 与 T **逐字节一致**
   —— `attention_backend` / `rms_norm` / `rotary_embedding` → `vendor.ascend`，
   `silu_and_mul` → `default.flagos`。同一张表下 F 连贯、T 退化。
2. **不是 flag_gems `silu_and_mul` kernel 算错。** 摘掉 vllm 直接调
   `flag_gems.silu_and_mul`（同镜像，F/T 各一次）：bf16 与 fp16 × `d ∈ {64, 9728}`
   × 连续/跨步视图，两编译器输出**逐字节相同**且与 CPU 参考一致（bf16 `d=9728`
   最大绝对差 `0.0291`，即 bf16 舍入量级）。
3. **两条黑名单杠杆均不成立**，不作为缓释手段：
   - yaml 键 `flagos_blacklist` 加 `silu_and_mul`：配置确被加载（日志
     `Using custom config from .../dispatch/config/ascend.yaml`），但路由表与基线
     **完全一致** —— 未生效。
   - 环境变量 `VLLM_FL_FLAGOS_BLACKLIST=silu_and_mul`（`vllm_fl/utils.py:119`，与 yaml
     键是**两条不同代码路径**）：serve 起不来，崩在**另一族** kernel ——
     `ConvertTritonIRToLinalgIR` → `strides must not be zero` → `triton-adapter-opt`
     SIGABRT，与 silu 无关。

4. **路由表不足以定位此缺陷**：它只反映 vllm_fl **插件层**派发，flag_gems 的
   **aten 层接管不在表内**。已排除项 1 的「F 与 T 路由表逐字节一致」与本根因不矛盾
   —— 被污染的是表里根本不出现的算子（见下第 2 条）。

**根因（2026-09-11 定位，含跨后端硬对照）**

链条：cann8.5.0 + triton-ascend 3.2.0 下 generic `index_select` 算错 → ATB rotary
组合算子内部吞下这份错误结果 → 0.24.0 的黑名单恰好堵住了本该触发回退的崩溃 →
污染的 q/k 直达 attention → 每次冷启动确定性复读 `!`。

1. **`_ascend.ops` 整包 import 失败，flag_gems 退化为 generic 算子集。** vendor triton
   3.2.0 无 `triton.experimental`（`importlib.util.find_spec("triton.experimental")`：
   F `True` / T `False`）；`_ascend/ops/__init__.py` 逐模块 import，其中
   `cholesky_solve.py:20` 在模块顶层 `import triton.experimental.tle.language`，抛
   `ModuleNotFoundError` 后**整包**失败（一个可选子模块缺失拖垮整个后端算子集）。
   flag_gems 自己的判词：`[Note] No specialized common operators were found for the
   ascend, generic common operators will be used by default.` 结果：`index_select` 在 F
   注册为 `_ascend.ops.index_select`，在 T **不在注册表内**，落到 generic
   `flag_gems/ops/index_select.py`。

2. **generic `index_select` 在 cann8.5.0 + triton-ascend 3.2.0 上算错，且非确定。**
   生产形状 `inp=(40960,128) dim=0 idx=(5,)` 实测 `bad=174~400 / 640`；同一输入三次得
   `[340, 220, 174]`（另几轮 355 / 375 / 392 / 400）→ 被掩码未写的 lane 保留了
   `torch.empty` 的复用显存。关掉 flag_gems 的 native 路径 `bad=0/640`；**同一探针在 F
   （走 `_ascend` 版）三次全 `bad=0/640`**。形状扫描（rows=40960）：`dim=0` 在 n=4…128
   **全部出错**，`dim=1` 在 n≥16 精确 → 不是 2 的幂 / tile 边界效应，且只打中 `dim=0`，
   正是 ATB rotary 的用法。

3. **ATB rotary 吞下这份错误结果。** `torch_npu._npu_rotary_embedding`
   （`vllm_fl/ops/rotary_embedding.py:49` → `vendor/ascend/impl/rotary.py:62`）内部走
   `torch.ops.atb.*`，其中对 cos/sin cache 做
   `aten::index_select(inp=(40960,128), dim=0, idx=(5,))` —— 形状与第 2 条完全一致，
   400 次/decode。被污染的 cos/sin 进入每个 attention head 的 q/k。

4. **两份 shipped `ascend.yaml` 的黑名单差异决定「吃不吃到污染」。** 0.24.0 是 0.20.2
   的严格超集，关键增量除 `linear` / `cumsum` / `pow_tensor_*` 外，是**三个
   `repeat_interleave_*`** —— 0.24.0 的 yaml 自带注释已写明：ATB rotary 路径内部用
   repeat_interleave 扩展 GQA 的 cos/sin，被 flag_gems 接管后 rank-3 的 pointwise copy
   在 triton_ascend 3.2.0 上编译失败（`ConvertTritonIRToLinalgIR` →
   `strides must not be zero`）。于是：
   - **0.20.2/T**：vendor rope 首次 decode 即抛 `MLIRCompilationError`（本轮实测复现，
     SIGABRT 于 `triton-adapter-opt`，栈 `repeat_interleave.py:75` →
     `copy_func_kernel_rank_3`），`CachedOp` 静默标记 `vendor.ascend` 失败并回退到
     `default.flagos` rope —— **因祸得福，绕过污染，绿**。同一缺陷在 0.20.2/T 上同样实测
     到（`bad=267~343/640`），只是被上游回退掩盖。
   - **0.24.0/T**：黑名单堵住了这次崩溃，vendor rope 跑完，把污染的 q/k 交给 attention
     —— **红**。

5. **cann9.0.0-910c 是硬对照。** 同 tag 的 0.24.0 镜像、同 T 路径、同探针：`bad=0/640`，
   rope 输出与 native **逐位相同**（`q=b391f204ee6e k=9e8aadea8226`）。缺陷是
   cann8.5.0 + triton-ascend 3.2.0 组合特有，与 910C 平台、镜像、插件均无关。

**两条实测为绿的 T 配置**，机理不同，此前记录的 `VLLM_FL_PREFER=vendor` 说明有误、在此更正：

- **精确方案：把 `index_select` 加入黑名单**（本轮 A/B：2/2 冷启动连贯，`cell-isT` /
  `cell-isT2`）。关键处在于**路由表与红基线逐字节一致**（仍是 `silu_and_mul` →
  `default.flagos`，rotary 仍是 `vendor.ascend`）而输出恢复连贯 —— 反向印证缺陷在
  **表外的 aten 层**，而非路由表能表达的任何一个算子。改 yaml 即可，不需改镜像。
- **`VLLM_FL_PREFER=vendor`（3/3 冷启动全绿）**：`use_flaggems()`
  （`vllm_fl/utils.py:84-93`）在 `VLLM_FL_PREFER` 非空且不等于 `flagos` 时**直接返回
  False**，`worker.py:252` 的 `fl_envs.USE_FLAGGEMS` 门随之关闭，`flag_gems.enable()`
  **根本不会被调用** —— 是**整体关掉 flag_gems**（含 aten 层接管），不是「只把
  `silu_and_mul` 换成 `vendor.ascend`」。粒度粗，仅作临时手段。

**处置**：cann9.0.0-910c 交付路径 = F/T 均可；cann8.5.0-910c 的 T 路径**按默认派发不可
交付**（`status_matrix.vllm0.24.0.yaml` 该后端 T 格已记 ❌、`note:` 记录根因），F 路径
为交付路径；需用 T 时以黑名单加 `index_select` 为缓释。

**上游归属**：坏的是 flag_gems 的 generic `index_select` kernel 在 triton-ascend 3.2.0
下的 codegen（或该 kernel 本身）；黑名单条目归属 vllm-plugin-FL 的
`dispatch/config/ascend.yaml`；「一个可选子模块缺失拖垮 `_ascend.ops` 整包注册」是
flag_gems 的脆弱点，也是本轮退化为 generic 的直接扳机。三项均不在 build-infra，属对外
hand-off。
