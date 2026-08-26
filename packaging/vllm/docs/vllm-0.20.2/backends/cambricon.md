# vllm 0.20.2 — cambricon neuware4.7.2 / neuware4.4.3

> 本文对应原报告第 2 部分 §2.7（MLU590 主记录）与 §2.11（T-only 兼容 shim）。
> 标准流程见 [`playbook.md`](../playbook.md)，决策见 [`decisions.md`](../decisions.md)。

## 2.7 cambricon-neuware4.7.2（MLU590：✅ E2E 通过，2026-08-08；2026-08-15 / 2026-08-26 复核）

**日期:** 2026-08-08（初验）；2026-08-15（复核，empty 黑名单删除 + index 回归）；2026-08-26（复核，flag_gems 5.3.5 / PR #5745 mask-logic 修复）
　**平台:** Cambricon MLU590　**节点:** `cambricon`
**driver/neuware:** 4.7.2　**镜像:** `flagos-runtime-cambricon-neuware4.7.2:2.1.2`（`1a2a53ebab3b`，全量升级包集）
**Python:** 3.12.13　**torch/torch_mlu:** 2.11.0+cpu / torch_mlu 2.11.0
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，全新 wheel build（cambricon 此前无 `+flagos` 产物）
**模型:** Qwen3-8B（`/data/zhaodeming/Qwen3-8B`）

cambricon 是**首个从零构建 `+flagos` wheel 的后端**（无可复用产物），故本次同时是
cambricon 的 wheel-build 首验。全链路 **serve + 推理一次跑通**，MLU590 上 Qwen3-8B
贪婪解码输出连贯英语，无数值 / 乱码问题。

### Repack —— 在 cambricon 上从零 build（cp312，源码用官方 flagos tarball）

MLU 无既有 `+flagos` 产物；xgrammar 为 cp312-locked 二进制，须本机 build。步骤：

1. **源码用官方 flagos tarball**（`vllm-0.20.2.tar.gz`，用户下载到节点 `/tmp`），
   **非** Aliyun pip sdist。tarball 无 git 元数据，setuptools-scm 会失败 →
   须设 `SETUPTOOLS_SCM_PRETEND_VERSION=0.20.2`。
2. empty build：`VLLM_TARGET_DEVICE=empty MAX_JOBS=$(nproc) pip wheel --no-build-isolation --no-deps`
   → `vllm-0.20.2-py3-none-any.whl`，`repack.py` 打 `+flagos` 后缀并递归 repack 间接依赖。
3. repack 需预建缓存目录：`mkdir -p <repack>/cache`（否则 `_download_dep_wheel` 报
   `FileNotFoundError: cache/...whl`）。

产物 4 个 wheel（vllm、xgrammar **cp312**、compressed-tensors、opencv-headless）。

### 安装 —— ✅ 单步，零泄漏

`flagos.net` 存储故障期间走本地 wheel + Aliyun extra-index 单步安装，实测零泄漏：

```
vllm:                   0.20.2+flagos          ✅  empty，cambricon 本地 build（cp312）
xgrammar:               0.2.3+flagos           ✅  cp312-cp312（per-Python 二进制）
compressed-tensors:     0.15.0.1+flagos        ✅  纯 py3
opencv-python-headless: 5.0.0.93+flagos        ✅  cp37-abi3（稳定 ABI）
torch / torch_mlu:      2.11.0+cpu / 2.11.0    ✅  from 镜像，无公有 torch/cuda/triton 链
```

无 pip 冲突，无 setuptools 降级（不同于 enflame）。

### 插件 —— ✅ 干净安装（--no-build-isolation，纯 Python）

`pip install --no-build-isolation -e .`，`VLLM_VENDOR` 未设 → 纯 `py3-none-any`
（`vllm-plugin-fl 0.2.0`）。无 enflame 的 setuptools 钉阻塞。

### serve + 推理 —— ✅ 成功（3 处 plugin patch + 1 处 flag_gems 黑名单 + 1 次算力清理）

MLU590 上带起 serve 需 4 个修复。前 3 个是 plugin 未覆盖 cambricon 的缺口，第 4 个是
flag_gems `empty` 内核在 MLU 上撞 triton grid 上限：

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 1 | `Vendor 'cambricon' not found in VENDOR_DEVICE_MAP`（`utils.py`） | `VENDOR_DEVICE_MAP` 无 cambricon 条目，`_get_vendor_device_field` 抛 ValueError | `utils.py:53` 加 `"cambricon": {"device_type": "mlu", "device_name": "mlu"}` |
| 2 | `NotImplementedError: not support graph`（`compilation/graph.py`） | `Graph` 类无 mlu 分支 | `graph.py:52-53` 加 `elif current_platform.device_type == "mlu": graph = torch.mlu.MLUGraph` |
| 3 | `OutOfResources: grid size 607744 > 65535`（`flag_gems/ops/empty.py:87`） | flag_gems `empty` 内核对 Qwen3 词表 embedding（151936×4096）算出 grid 607744，超 MLU triton grid 上限 65535 | 黑名单 `empty`。**定稿走 plugin 内建配置 `dispatch/config/cambricon.yaml`（Priority 3），非 env**：文件名须匹配 `current_platform.vendor_name`（`cambricon`）才被 `get_config_path()` 自动加载。已容器验证：不设 `VLLM_FL_FLAGOS_BLACKLIST` 时 `use_flaggems_op('empty')=False`、serve 启动完成、推理连贯（隔离测试另证 `flag_gems.enable(unused=)` 键是 `empty` 而非 registry 名 `empty.memory_format`） |
| 4 | 内存不足（62.68 GiB free < 67 GiB） | 前次崩溃留下孤儿 `VLLM::EngineCore` 进程占住 MLU0 约 16.5 GiB | 清理孤儿进程 + `MLU_VISIBLE_DEVICES=0` 单卡 |

修复后 serve 启动：`init engine (profile, create kv cache, warmup model) took 406.84 s
(compilation: 96.79 s)`，KV cache 350,240 tokens，`Application startup complete`。

**首次推理**首 token 延迟高（首请求逐 shape 编译 triton 内核，60s curl 超时；加长到
300s 即返回）；`_cambricon/ops/mean.py` 等 flag_gems cambricon 算子活跃，无错。

### 2026-08-15 复核（2.1.2 镜像 / flag_gems 5.3.4）：empty 黑名单可删 ✅，index op 回归 → flag_gems 根因修复

**empty ✅（黑名单已删，无回归）：** 2.1.2 镜像装 flag_gems **5.3.4**（已含
cambricon 专属 `_cambricon/ops/empty.py` 分块修复，PR #4435）。将 `cambricon.yaml`
的 `flagos_blacklist` 清空为 `[]` 实测：serve 启动完成、推理连贯 → **`empty` 黑名单
可安全删除**（这正是 §2.7 初验时"根治 = 升 flag_gems 到含 #4435 的版本"的兑现）。

**index op 回归（E2E 确定性崩溃，黑名单已加）：** 复核过程中首次请求即触发 flag_gems
cambricon `index` op 在 **flagtune 自动调参 bench** 阶段崩溃，EngineCore 直接死亡
（HTTP 500 / EngineDeadError）。复现路径与完整证据链：

- **触发点：** `model_runner.py:4145` `sample_hidden_states = hidden_states[logits_indices]`
  → `_cambricon/ops/index.py` `_index_func`（461）→ code_cache `_index_wrapper` → triton autotune。
- **崩溃：** Triton MLU 后端 `compiler.py:722` `make_optimized_linalg` 的
  `PassManager::run` 抛 `RuntimeError: PassManager::run failed`，原始 MLIR 报
  `'tensor.expand_shape' op expected dimension 0 of collapsed type to be static value of 4`
  （`AutoTileForTritonPass`，发生在 `genesis.num_stages = 2`、`linalg_ext.scatter`、
  `tensor.extract_slice [4, %76]`、`tensor.expand_shape %81 [[0,1],[2]] output_shape [1,4,4096]`
  的 bench 阶段，shape (15, 4096)、BLOCK_SIZE0=4 / BLOCK_SIZE1=4096、num_warps 4）。
- **为什么 autotuner 救不了：** RuntimeError 在 triton `autotuner.py:160` `_bench` 内抛出，
  但**不在** triton 的 `(OutOfResources, CompileTimeAssertionFailure, PTXASError)` catch 列表
  → 无法转 `inf` 跳过该 config → 直接传播 → EngineCore 死。
- **与 DB 中 inf 行的关系（已厘清，二者无关）：** `TunedConfig_cambricon_triton_3_4.db`
  (15, 4096) 的 inf 行是 **ns=2 + b1=4096 的 NRAM 超限**（nw=4: 609024 / nw=1: 856400 >
  MLU590 硬件上限 524288 → OutOfResources → 被 tuner 正确捕获记 inf），18 个 bench config
  中其余 16 个 standalone 全部 PASS。expand_shape 崩溃是 **E2E 上下文专属**（inductor wrap +
  BACKED dynamic shapes + VLLM_COMPILE=3），standalone 不触发。
- **修复（两处，E2E 已验证）：** ① 过渡：`vllm_fl/dispatch/config/cambricon.yaml`
  `flagos_blacklist: [index]`（与 `empty` 同机制：Priority 3 内建配置，回退 torch_mlu）。
  ② 根因：**flag_gems PR #5510**（libentry `bench()` 将任意 `RuntimeError` 视为 inf
  非候选，防后端编译 bug 杀进程；`_cambricon/tune_configs.yaml` index 块删
  `BLOCK_SIZE1=4096`——该 config 是崩溃触发者，且 ns=2 下 4096 宽 tile 恒超 NRAM
  本就不能赢）。**实测：** 去掉黑名单（`flagos_blacklist: []`）重启 serve 后，原崩溃
  请求 200 返回正确输出，连续请求 EngineCore 存活、0 ERROR。黑名单在 #5510 随
  flag_gems 发布前保留作过渡。
- **遗留：** 原始 MLIR reproducer 已留存（容器 `/tmp/serve534_crash_index2.log`）。厂商
  hand-off 文档（flag_gems/MLU Triton AutoTileForTritonPass expand_shape bug）待整理。

### 2026-08-26 复核（flag_gems 5.3.5 / PR #5745 mask-logic 修复）：✅ E2E 通过

**背景：** FlagGems PR #5745（`fix/cambricon-tensor-mask-logical-ops`，commit 9737224bf）把
cambricon/MLU 后端 23 个文件里对多元素 tensor mask 的 Python `and`/`or`/`not` 机械替换为
元素级 `&`/`|`/`~`（`&` 优先级高于 `<` 处补括号），触发算子是 argmax。已合并并重打
flag_gems **5.3.5** tag，cambricon runtime 镜像重打（flat tag `2.1.2`，
sha256 `907c1c8285daabfdd6bbc136b34be686b99a1563d532b30f880819945a6548af`）。本次在
MLU590 真机复核改后算子跑出**正确结果**（而非仅"不崩"）。

**可复现配方（全部走已上架制品，无本地 build / 无手工 patch）：**

- 镜像：`flagos-runtime-cambricon-neuware4.7.2:2.1.2`（sha256 `907c1c8285da…`，flag_gems 5.3.5）
- vllm：`vllm==0.20.2+flagos` 单步 `pip install`（wheel 已上架 `flagos-pypi-cambricon`，单步零泄漏）
- 插件：vllm-plugin-FL **PR #411 head `b954912`**（`cambricon.yaml` `flagos_blacklist: [index]`）
- serve：Qwen3-8B TP=1 / max-len 4096 / mem-util 0.85，`Application startup complete`（编译 ~11 min）
- 推理：2 次 chat completion 均 200、连贯。`"Reply with exactly the words: hello world"`
  → 先 `<think>` 后输出 `hello world`，`finish_reason=stop`；另一问 `2+2` 思考推理正确。

**结论：** flagos dispatch 活跃（`OpManager: 35 ops / 61 impls`，`attention_backend →
default.flagos`），改后 mask-logic 算子（含 argmax——温度 0 贪婪采样走 argmax 路径）在 E2E
中运行，输出无乱码、无数值错误 → **PR #5745 修复正确**。

**黑名单现状：** flag_gems 5.3.5 **不含** PR #5510（`index` 根因修复，仍 OPEN——
实测 5.3.5 的 `_cambricon/tune_configs.yaml` index 块仍含 `block_size1: [1024, 2048, 4096]`），
故 `cambricon.yaml` 的 `flagos_blacklist: [index]` 保留（本次 PR #411 head 已正确携带）。


### Stack 验证（cambricon-neuware4.7.2，✅ E2E 通过 2026-08-08）

```
setuptools:   稳定（无降级）           ✅
torch/torch_mlu: 2.11.0+cpu / 2.11.0  ✅  from 镜像
vllm:         0.20.2+flagos          ✅  empty，cambricon 本地 build（cp312）
vllm_fl:      0.2.0 + 3 patch        ✅  纯 Python（VENDOR_DEVICE_MAP / MLUGraph / —）
flag_gems:    5.3.4（empty 分块修复已含，见 PR #4435）  ✅  empty 黑名单已删；
                                          index 根因修复已提 PR #5510（libentry 防护 +
                                          删 b1=4096 调参项）；黑名单为过渡（发布前保留）
MLU device:   ✅ MLU0 单卡           MLU590
vllm import:  ✅
vllm serve:   ✅  application startup complete（Qwen3-8B TP=1, max-len 4096, mem-util 0.85）
Inference:    ✅  连贯英语——"What is the capital of France?" → 正确推理至 Paris；
                  finish_reason=length（64 token 上限），无乱码/dtype/libdevice 错
                  POST /v1/chat/completions 200 OK，生成 ~4.3 tokens/s
```

### plugin 侧修复（3 处代码 + 2 次黑名单演进，均容器内验证，已入 PR #411）

| 修复 | 文件 | 性质 |
|---|---|---|
| `VENDOR_DEVICE_MAP` 加 cambricon → mlu | `vllm_fl/utils.py:53` | plugin 未覆盖 cambricon（真实缺口） |
| `Graph` 加 mlu → `torch.mlu.MLUGraph` 分支 | `vllm_fl/compilation/graph.py:52` | plugin `Graph` 无 mlu 分支（真实缺口） |
| 黑名单 `index`（内建配置；`empty` 已随 5.3.4 修复移除） | `dispatch/config/cambricon.yaml` `flagos_blacklist: [index]` | `index` op flagtune bench 时 expand_shape/AutoTileForTritonPass 崩溃（见 2026-08-15 复核）；回退 torch_mlu。**过渡**：根因已修 flag_gems PR #5510，发布前保留。`empty` 同机制黑名单于初验加入、5.3.4（PR #4435）落地后删除。定稿走 plugin 内建配置（非 env），文件名匹配 vendor_name=`cambricon` 才自动加载 |

本地补丁副本：`/tmp/camb-patches/{utils.py,graph.py}`。serve 脚本：
`/tmp/camb_serve6.sh`（复核用 `/tmp/launch_serve534.sh`，日志 `/tmp/serve534.log`）。

### MLU590 约束记录

- **triton grid 上限 65535**（vs NV 2^31-1）：任何按元素总数算 grid 的 flag_gems
  内核在大张量上都会撞（本次为 `empty`；其它大算子潜在同类风险）。
- **num_warps 上限 4**：超出触发 fallback warning（非致命，仅噪声）。
- `torch.mlu.MLUGraph` 存在（对应 CUDAGraph），plugin graph 分支可直接用。

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| 3 处修复对齐 Mac 源码并提 PR | ✅ 已提 | **PR #411**（flagos-ai/vllm-plugin-FL）：VENDOR_DEVICE_MAP cambricon→mlu + graph.py mlu→MLUGraph（2 处代码，通用缺口非 cambricon hack）+ `dispatch/config/cambricon.yaml`（内建配置非 env）。三处全部 E2E 验证 |
| `empty` 黑名单固化 → 2026-08-15 已随 5.3.4 移除 | ✅ 已入 PR #411 | 初验定稿为内建配置 `dispatch/config/cambricon.yaml`（非 env）。5.3.4 含 #4435 分块修复后，复核实测 `flagos_blacklist: []` serve + 推理正常 → PR 已删 `empty` 黑名单 |
| `index` op 崩溃根因修复 | ✅ 已提 flag_gems PR #5510 | 两处：libentry `bench()` RuntimeError→inf 防护 + `_cambricon` index 调参删 `BLOCK_SIZE1=4096`。去黑名单 E2E 实测通过（首请求 200、EngineCore 存活）。发布前 plugin 黑名单保留作过渡 |
| flag_gems `empty` MLU grid 分块 | ✅ 上游已修，已进 5.3.4 | **PR #4435**（2026-08-07 合入 master）cambricon 专属 `_cambricon/ops/empty.py`（grid 上限 `TOTAL_CORE_NUM` + grid-stride 循环 + int64 offset）。5.3.3 发布早于 #4435 故不含；2.1.2 镜像装 5.3.4 已含 → `empty` 黑名单删除且实测无回归 |
| cambricon `+flagos` wheel 上架 per-vendor index | ✅ 已上传 | 4 个 wheel（vllm / xgrammar cp312 / compressed-tensors / opencv-headless）已上架 `flagos-pypi-cambricon`；不再依赖本地 wheel |
| index expand_shape / AutoTileForTritonPass 厂商 hand-off | ⬜ 待整理 | flag_gems/MLU Triton 编译 bug（libentry 防护已绕开）；reproducer 已留存 `/tmp/serve534_crash_index2.log`，文档待补 |

**相关提交：** 2026-08-15 复核后 **PR #411 分支已更新**（`b954912`，仅 cambricon.yaml：
删 `empty` 黑名单、加 `index` 黑名单）。**根因修复 = flag_gems PR #5510**
（`fix/cambricon-index-expand-shape`：libentry RuntimeError 防护 + 删 `BLOCK_SIZE1=4096`），
去黑名单 E2E 验证通过；PR #411 的 `index` 黑名单保留为过渡，待 #5510 随 flag_gems
发布后删除。wheel 在 cambricon 镜像内从官方 tarball 重新 build + repack。

## 2.11 cambricon-neuware4.4.3（MLU590：✅ E2E 通过，2026-08-26；T-only，无 FlagTree）

**日期:** 2026-08-26
　**平台:** Cambricon MLU590　**节点:** `cambricon`
**driver/neuware:** 4.4.3　**镜像:** `flagos-runtime-cambricon-neuware4.4.3:2.1.2`
**Python:** 3.10.20　**torch/torch_mlu:** 2.7.1+cpu / 1.29.2+torch2.7.1
**triton:** 3.2.0+mlu1.7.2　**flag_gems:** 5.3.5　**numpy:** 2.2.6
**目标:** vllm 0.20.2+flagos + vllm-plugin-FL 单步安装，serve + 推理
**模型:** Qwen3-4B（`/data/models/Qwen/Qwen3-4B`）

cambricon 4.4.3 是 **T-only 特例**（无配套 FlagTree，用户确认），故本后端只验 Triton
单路径。与 4.7.2（§2.7）的关键差异：Python 3.10（vs 3.12）、torch 2.7.1+cpu（vs
2.11.0）、triton 3.2.0+mlu1.7.2（vs 3.4.0+mlu2.1.1）。旧版工具链在 serve 路径上暴露了
4.7.2 未触及的 5 个兼容缺口，全部在 **vllm-plugin-FL 侧**修复（不碰 vllm 本体），已随
PR #411 上提。

### Repack / 安装 —— ✅ 单步，零泄漏

vllm `0.20.2+flagos` cp310 wheel 与 xgrammar cp310 wheel（xgrammar 为本后端首个 cp310
产物，见下）均已上架 `flagos-pypi-cambricon`，单步 `pip install` 零泄漏。torch / torch_mlu
均 from 镜像，无公有 torch/cuda/triton 链。xgrammar 为 cp310-locked 二进制，须本机 build
（与 4.7.2 的 cp312 分属不同 Python，不可复用）。

### 插件 —— ✅ 干净 wheel build（--no-build-isolation，纯 Python）

vllm-plugin-FL **PR #411 head `b954912`**（base release/0.2）。wheel
`vllm_plugin_fl-0.2.1+gb954912.d20260826-py3-none-any.whl` 在容器内
`pip wheel --no-build-isolation` 构建（`SETUPTOOLS_SCM_PRETEND_VERSION=0.2.1+gb954912.d20260826`；
源码 = `git archive HEAD` 解包，可复现，无手工 patch）。

### serve + 推理 —— ✅ 成功（5 处兼容 shim，均在 plugin 侧）

serve ready ~125s，`Application startup complete`，completion HTTP 200，Qwen3-4B 输出连贯：

```
prompt: "The capital of France is" → " Paris. The capital of Germany is Berlin.
The capital of Italy is Rome."（finish_reason=length，16 token 上限）
```

| # | 症状 | 根因 | 修复（`vllm_fl/__init__.py` / `worker/model_runner.py`） |
|---|---|---|---|
| 1 | `AttributeError: torch.float4_e2m1fn_x2` | 该 dtype 仅存在于 CUDA torch 2.7+，cambricon torch 2.7.1+cpu 无 | import 前注入 `_torch.float4_e2m1fn_x2 = _torch.uint8` 哨兵（**已有**，源自 #176 MUSA） |
| 2 | `AttributeError: get_mlu_view_from_cpu_tensor`，torch._inductor init 中止 | torch_mlu 把 `_C::get_mlu_view_from_cpu_tensor` 注册为 CIA op，但无 `torch.ops._C` Python handle，`_materialize_cpp_cia_ops` getattr 抛错 | 覆盖为 tolerant 版：getattr 失败即跳过该 op |
| 3 | `KeyError: 'aten::copy_'`（flag_gems copy_ hook） | flag_gems 5.3.5 用 `torch.library.get_kernel()` 填 torch_ops_map，该 API 仅 torch 2.8+，2.7.1 无 → map 空 | 提供 2.7.1 兼容 get_kernel：`OpOverload.redispatch(CompositeExplicitAutograd keyset)` |
| 4 | `RuntimeError: Backend doesn't support synchronizing all streams` | plugin `_accelerator_synchronize` 走 `torch.accelerator.synchronize()`，无 mlu 分支 | `model_runner.py` 加 `elif device_type == "mlu": torch.mlu.synchronize()` |
| 5 | `TypeError: task_type='block'`（triton launch kwarg） | flag_gems 5.3.5 cambricon 后端 emit `task_type='block'`，triton 3.2.0+mlu1.7.2 不支持 | `JITFunction.run` 剥掉 task_type kwarg（须在 `import torch_mlu` 之后 patch，避免 triton init 循环导入） |

其中 #1 是既有缺口（float4 哨兵来自 PR #176 MUSA 支持），#2~#5 为本后端新暴露、本次
上提（PR #411 head `b954912`：CIA/get_kernel/task_type 三 shim + mlu sync）。

### Stack 验证（cambricon-neuware4.4.3，✅ E2E 通过 2026-08-26）

```
Python:       3.10.20                 ✅
torch/torch_mlu: 2.7.1+cpu / 1.29.2   ✅  from 镜像
triton:       3.2.0+mlu1.7.2          ✅  T-only（无 FlagTree）
vllm:         0.20.2+flagos           ✅  cp310，单步安装
vllm_fl:      0.2.1+gb954912.d20260826          ✅  纯 Python wheel（5 处 shim）
flag_gems:    5.3.5                   ✅
vllm serve:   ✅  application startup complete（~125s，Qwen3-4B TP=1）
Inference:    ✅  HTTP 200，completion 输出连贯
```

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| 4 处新 shim 上提 plugin | ✅ PR #411 | base release/0.2，head `b954912`（#2~#5；#1 float4 已有） |
| `deps_app.vllm0.20.2` 加 4.4.3 | ✅ configs.yaml | `neuware4.4.3.deps_app.vllm0.20.2: []` |
| xgrammar cp310 wheel | ✅ 已上架 | 本后端首个 cp310 xgrammar，`flagos-pypi-cambricon` |
| docs flag_gems 5.3.4 → 5.3.5 | ⬜ 待重渲 | `docs/content/**/runtime/*.md` 仍 5.3.4，configs.yaml/data 已 5.3.5 |
