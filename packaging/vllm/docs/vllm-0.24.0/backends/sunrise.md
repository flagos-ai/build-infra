# vllm 0.24.0 — sunrise tangrt1.2.0

> 本文对应原报告 §11。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 11. sunrise（TANGRT 1.2.0）详细记录（2026-08-19）

sunrise 是 python 3.10，0.24.0 empty wheel 绑定 CPython 小版本
（`cp310-cp310`），因此本后端验证前置 = **构建 cp310 empty wheel**（§11.1）。
插件侧移植比 [ascend §10](ascend.md) 小得多：sunrise 的 `attention.py` 已是
0.24.0 接口形态，改 CUSTOM 注册即可；`patch.py` 5 个 patch 目标全部存在于
0.24.0，另补一个 `memory_stats` 合成（§11.2）。E2E 走
[0.20.2 §2.9](../../vllm-0.20.2/backends/sunrise.md) 结论的**交付路径 =
`compiler triton`**（FlagTree flash-attn decode 挂死，详见该节）。

### 11.1 构建：cp310 empty wheel（Phase A）

- 命令：`./build-and-repack.sh sunrise-tangrt1.2.0 --vllm-version 0.24.0`
  （build 容器需要 `DOCKER_RUN_FLAGS="--privileged -v /dev:/dev"`，
  ptpu 平台在 torch import 时无设备会 abort）
- 产出：`vllm-0.24.0+flagos`（cp310-cp310，empty 构建 + repack 单步
  安装），连带 `compressed-tensors 0.17.0+flagos`、
  `opencv-python-headless 5.0.0.93+flagos`、`xgrammar 0.2.3+flagos`
  一套（ABI 绑定本 vendor 镜像的 python/arch，保持单 index 完整）。
- 上传：未 `--upload`（用户持有 twine 凭据），节点侧从本地
  `/opt/wheels` 安装验证。

### 11.2 插件移植（Phase B，分支 feat/sunrise-v024）

基线 v0.3.0-dev（5b592be，含 torchvision guard
[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)），2 个文件改动：

1. **`impl/attention.py` 改 CUSTOM 注册**（ascend
   [VPF #387](https://github.com/flagos-ai/vllm-plugin-FL/pull/387) 同款模式）：
   `get_name()` 返回 `"CUSTOM"` + 模块级
   `register_backend(AttentionBackendEnum.CUSTOM,
   "vllm_fl.dispatch.backends.vendor.sunrise.impl.attention.
   AttentionFLBackend")`。sunrise 原 `get_name()` 返回 `"TRITON_ATTN"`，
   恰好是 0.24.0 合法成员，但为语义干净 + 与 ascend 模式统一，采用
   CUSTOM 显式占位成员（registry 注释"must be registered before use"）。
2. **`patch.py` 新增 `patch_accelerator_memory_stats()`**：合成
   `torch.ptpu.memory_stats()`，供 FL worker KV-cache 定容读取
   `"allocated_bytes.all.peak"`。torch.ptpu 只有
   `max_memory_allocated`/`memory_reserved`，无 torch.cuda 风格
   memory_stats 字典；新函数从 peak API 合成 FL worker 用到的两个 key，
   guard 永不覆盖真实实现。

### 11.3 serve + 推理（Phase C，Qwen3-8B，TP1）

- 容器：`--privileged -v /dev:/dev` 启动，`pt_smi` 确认设备。
- 安装：`vllm==0.24.0+flagos`（cp310 wheel）+ vllm-plugin-fl editable
  （`/opt/vllm-plugin-FL`，`--no-build-isolation`）。
- 编译器：`compiler triton`（vendor triton 3.6.0.1+git0a5cfb35）。
- **模型为 `/models/Qwen3-8B`**（该平台无 Qwen3-4B，矩阵
  "Qwen3-4B"约定在此单元格不适用，同 [mthreads §8](mthreads.md) 先例）。
- serve：`--port 8031 --gpu-memory-utilization 0.6 --enforce-eager
  --trust-remote-code --max-model-len 2048 --dtype bfloat16` →
  `Application startup complete`。算子路由：`attention_backend`
  `default.flagos`（TritonAttentionBackend）因需 CUDA 失败 →
  **fallback `vendor.sunrise`**（CUSTOM 注册生效）；`rms_norm`/
  `rotary_embedding`/`silu_and_mul` 走 `default.flagos`。5 个 sunrise
  patch 全部生效（含新 memory_stats）；KV cache 31,232 tokens；
  init engine 19.43s。
- 推理：knowledge 连贯 ✅ —— `The capital of France is` → " Paris.
  The capital of Italy is Rome. The capital of Spain is Madrid. ..."
- 指纹：system_fingerprint `vllm-0.24.0-6c831be5`；torch
  2.11.0+cpu / torch_ptpu 0.2.3+torch2.11 / flag_gems 5.3.4 /
  triton 3.6.0.1+git0a5cfb35。
- **非致命警告**：FlagCX stream adapter patch 报
  `No module named 'plugin'`（FLAGCX_PATH 未设）—— TP1 无影响，
  TP>1 需设置 FLAGCX_PATH 后复验。

### 11.4 排障记录：`memory_stats` AttributeError

首次 serve 崩 `RuntimeError: Engine core initialization failed`，
根因 = FL worker `determine_available_memory` 调
`torch_device_fn.memory_stats().get("allocated_bytes.all.peak", 0)`，
而 `torch.ptpu` 无 `memory_stats`（节点 probe 确认：
`AttributeError: module 'torch_ptpu.ptpu' has no attribute
'memory_stats'`；torch.ptpu 的 memory API 只有
`max_memory_allocated`/`memory_reserved`/`memory_allocated`/
`reset_peak_memory_stats`/`mem_get_info`/`empty_cache`）。

修复落在插件 patch.py（§11.2 第 2 条），节点侧先 probe 验证
（`has memory_stats after: True`，`memory_stats() =
{'allocated_bytes.all.peak': 0, 'reserved_bytes.all.peak': 0}`
分配前），再重挂 serve → 全绿。该 shim 与 [metax](metax.md)
`accelerator_compat.py` 的 torch.accelerator 补丁同一模式，只改
插件、不改官方 vLLM。

### 11.5 补充：FlagTree（sunrise）wheel 重建 —— 解码挂死已修复（2026-08-19）

[0.20.2 §2.9](../../vllm-0.20.2/backends/sunrise.md) 定位的 FlagTree
flash-attn 解码 kernel 挂死，根因锁定在**上游 FlagTree 旧 vendor 标签
0.6.0+sunrise3.6（[FlagTree #978](https://github.com/flagos-ai/FlagTree/pull/978)
之前）的 sunrise 后端代码生成缺陷**；
[FlagTree #978](https://github.com/flagos-ai/FlagTree/pull/978) 重写了
sunrise backend pass pipeline 并删掉 `add_split_dot`（疑似修复点）。
本次将 sunrise wheel 构建固化到 `packaging/flagtree/sunrise`
（[build-infra #447](https://github.com/flagos-ai/build-infra/pull/447)→[build-infra #450](https://github.com/flagos-ai/build-infra/pull/450)
链，2026-08-19 合入 main），**从 FlagTree main（含
[FlagTree #978](https://github.com/flagos-ai/FlagTree/pull/978)）重建
wheel**，并做了 A/B 实证：

| 项目 | 旧 vendor 标签（pre-978） | 重建 wheel（post-978） |
|------|--------------------------|------------------------|
| 解码 tok/s（warm，Qwen3-8B） | 0.4（非终止） | **2.4~2.5（终止）** |
| decode 挂死 | 是（120s HTTP 超时） | 否 |
| 输出连贯 | 无 | ✅ knowledge 连贯 |

A/B 结论：**重建 wheel 修复了解码挂死**；F 路径（`compiler flagtree`）
从"沿用 [0.20.2 §2.9](../../vllm-0.20.2/backends/sunrise.md) 挂死
结论"升级为 ✅（[§15](../index.md) 已同步）。

**构建 gate（全部通过，CI 内置）**：干净版本号（无 `.git<sha>` 后缀）、
cp310 标签、22.04 可加载（无 GLIBC_2.38/GLIBCXX_3.4.31+ 符号）、
pybind11 internals **v12**（与 sunriseTritonPlugin_v0.6.0.4 ABI 匹配；
metax 插件是 v11，两者相反）、`triton.language.extra` 同时带
`ptpu`+`tang` 别名（flag_gems ≤5.3.4 引用 tang）、RUNPATH 含 `$ORIGIN`。

**RUNPATH 修复（[build-infra #450](https://github.com/flagos-ai/build-infra/pull/450)）**：`CMAKE_INSTALL_RPATH` 只作用于 install 期，
而 wheel 直接打包 build-tree 的 `libtriton.so`（无 `cmake --install`），
必须补 `-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON` 才会把 `$ORIGIN` 写到
build-tree .so 上；否则安装到 `/opt/flagtree` 后 loader 找不到同目录的
`sunriseTritonPlugin.so`（旧 RUNPATH 是绝对路径
`/usr/local/lib/python3.10/dist-packages/triton/_C`）。

**节点复验（无 workaround）**：`rm -rf /opt/flagtree/triton ...` 后干净重装
新 wheel，安装后 libtriton.so md5 `924b1c0d`（= wheel 内 md5），
`readelf -d` RUNPATH `[$ORIGIN]`；**不带** `LD_LIBRARY_PATH=/opt/flagtree/
triton/_C:...`、**不做**手动 tang 软链，`import triton`（3.6.0）+
`triton.language.extra.tang/ptpu` + `flag_gems`（5.3.4）全部 OK；
serve + 推理 E2E 通过（`Application startup complete`，knowledge
连贯，64 tokens 26.7s = 2.39 tok/s）。wheel 已上传 `flagos-pypi-sunrise`
（`upload=true`，沿用原版标签 0.6.0+sunrise3.6，drop-in 替换）。

**构建约束（固化在 Containerfile）**：Ubuntu 22.04（glibc 2.35）+
clang-14/lld-14（sunrise 后端 flags 是 clang-only
`-Werror -Wno-covered-switch-default`，gcc 会 -Werror=attributes 挂掉）；
系统 python3.10（apt）+ pip 走 aliyun 镜像（runner 到 pypi.org 不通）；
sunrise deps（LLVM/plugin/triton toolkits）从预置 URL 下载并 md5 门禁。

### 11.6 app 镜像 serve E2E（2026-08-19~20）

- 镜像：`harbor.baai.ac.cn/flagos-app/vllm0.24.0-sunrise-tangrt1.2.0:2.1.2-0.2.0_g687217a.d20260819`
  （2026-08-19 push 至 flagos-app，与原
  `flagos-dev/vllm-sunrise-tangrt1.2.0:2.1.2` tag 同一镜像，docker image
  id `sha256:22a8f7f1...`，与节点本地镜像逐字节一致）
- 版本指纹：vllm `0.24.0+flagos`（cp310 empty wheel，单步安装）；
  vllm-plugin-fl `0.2.0+g687217a.d20260819`（vendor PyPI wheel，非
  editable —— 同一 [VPF #391](https://github.com/flagos-ai/vllm-plugin-FL/pull/391)
  代码，同 §11.2/11.3）；torch 2.11.0+cpu /
  torch_ptpu 0.2.3+torch2.11 / flag_gems 5.3.4 / xgrammar 0.2.3+flagos /
  compressed-tensors 0.17.0+flagos；编译器 = vendor triton
  3.6.0.1+git0a5cfb35（`compiler triton`，`VLLM_PLUGINS=fl` 烘焙）
- 启动：`/flagos/bin/vllm serve`（`compiler triton` 烘焙，`--privileged
  -v /dev:/dev`）：`--model /models/Qwen3-8B --gpu-memory-utilization 0.6
  --enforce-eager --trust-remote-code --max-model-len 2048 --dtype bfloat16`
- 启动：`Application startup complete`；算子路由同 §11.3 ——
  `attention_backend` `default.flagos` 因 CUDA unavailable 失败 →
  **fallback `vendor.sunrise`**（CUSTOM 注册生效）；容器稳定运行 9h+，
  期间 0 崩溃标记
- 推理（2026-08-20 00:21 复测，system_fingerprint `vllm-0.24.0-6c831be5`，
  与 §11.3 同一 wheel/plugin）：
  - knowledge：`The capital of France is` → " Paris. The capital of
    Italy is Rome. The capital of Spain is Madrid. ..." ✅
  - math：`What is 7 times 8? Answer:` → " 56. What is 9 times 6? ..." ✅
- 崩溃标记：0（serve 日志无 Traceback / ERROR / EngineDeadError；容器
  存活；Avg generation throughput 6.4 tok/s）

---
