# vllm 0.20.2 — ascend cann9.0.0

> 本文对应原报告第 2 部分 §2.8（含 2026-08-24 双后端 F/T 全通后续）。
> 标准流程见 [`playbook.md`](../playbook.md)，决策见 [`decisions.md`](../decisions.md)。

## 2.8 ascend-cann9.0.0（Ascend 910B4 aarch64：✅ E2E 通过，2026-08-10）

**日期:** 2026-08-10　**平台:** Ascend 910B4（aarch64）

**driver/CANN:** npu-smi 26.0.rc1 / CANN 9.0.0　**镜像:** `flagos-runtime-ascend-cann9.0.0:2.1.2`（Phase B 用其快照）

**Python:** 3.11.15　**torch/torch_npu:** 2.10.0+cpu / 2.10.0　**triton:** 3.5.1

**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，全链路 serve + 推理

**模型:** Qwen3-4B（`/data/models/Qwen/Qwen3-4B`，modelscope 下载 7.6G）

ascend 是此前 flag_gems `j0`/`log2` 缺失致 import 崩溃的两个后端之一，故本次 E2E
同时是**修复后 5.3.4 wheel 的在硬件确认**。全链路 serve + 推理一次跑通，910B4 上
Qwen3-4B 贪婪解码输出连贯英语。这也是首个 **aarch64 + Python 3.11** 组合的 repack。

### Repack —— 复用 Phase A 产物（aarch64 / cp311）

Phase A（2026-08-10，镜像构建容器内）产出 4 个 `+flagos` wheel，零泄漏扫描通过，
平台 tag 正确，用户已上架 `flagos-pypi-ascend`：

```
vllm:                   0.20.2+flagos     ✅  empty，py3-none-any
xgrammar:               0.2.4+flagos      ✅  cp311-cp311-manylinux_2_26_aarch64（py3.11+aarch64）
compressed-tensors:     0.15.0.1+flagos   ✅  纯 py3
opencv-python-headless: 5.0.0.93+flagos   ✅  cp37-abi3-manylinux_2_28_aarch64（稳定 ABI）
```

### 安装 —— ✅ 单步 + 插件干净安装

`vllm==0.20.2+flagos` 从 `flagos-pypi-ascend` 单步安装，torch/torch_npu 从镜像保留，
无公有 torch/cuda/triton 链。`vllm-plugin-FL` 走 `pip install --no-build-isolation -e .`
（`VLLM_VENDOR` 未设 → 纯 `py3-none-any`，`vllm-plugin-fl 0.0.0+gf4ebc258f`）。

### serve + 推理 —— ✅ 成功（3 处修复）

1. **症状：** import 崩溃 `libdevice has no attribute 'j0'`

   **根因：** 镜像烘焙的是 **旧** 5.3.4 wheel（重推前），FlagTree
   `triton.language.extra.cann.libdevice` 缺 `j0`/`log2`，`_patch_missing_symbols`
   无 fallback 可打

   **修复：** 从 `flagos-pypi-ascend` **强制重装 5.3.4**（重推后 wheel）→
   `j0=True log2=True`。**即用户重推 5.3.4 的硬件确认**

2. **症状：** serve 启动崩溃 `coreDim is invalid (value 0)`（EngineCore init）

   **根因：** 模型构造 `register_buffer("_k_scale", torch.tensor(1.0))` 经
   `aten::lift_fresh` 被 flag_gems 拦截，标量 tensor 算出零 grid，NPU KernelLaunch coreDim=0

   **修复：** `dispatch/config/ascend.yaml` `flagos_blacklist` 加 `lift_fresh` /
   `lift_fresh_copy` / `_to_copy`（纯拷贝，回退 torch_npu 无损）

3. **症状：** 推理崩溃 `OSError: Could not load this library: .../libatb.so`
   （`_npu_reshape_and_cache` / `_npu_rotary_embedding`）

   **根因：** 基础镜像 `vendor.sh` 仅设 CANN toolkit `LD_LIBRARY_PATH`，**未 source
   NNAL/ATB `set_env.sh`** → `ATB_HOME_PATH` 空，ATB 后端算子（reshape_and_cache /
   rotary_embedding）加载失败

   **修复：** serve 前 `source /usr/local/Ascend/nnal/atb/set_env.sh`（解析到 `cxx_abi_1`，
   libatb 就位）。**镜像侧缺口**——应烘焙进 base image env（见待办）

修复后 serve 达 `Application startup complete`（KV cache 2048-token / 50.5x 并发，NPU 1）。
**首次推理**首 token 延迟高（首请求逐 shape 编译 triton/NPU 内核，60s curl 超时 →
加长即返回）；rms_norm/rotary/silu_and_mul 均正确 dispatch，全程 0 error。

### Stack 验证（ascend-cann9.0.0，✅ E2E 通过 2026-08-10）

```
torch/torch_npu: 2.10.0+cpu / 2.10.0  ✅  from 镜像
triton:       3.5.1                    ✅  （+ triton_ascend）
vllm:         0.20.2+flagos           ✅  empty，复用 Phase A aarch64 产物
vllm_fl:      0.0.0+gf4ebc258f        ✅  纯 Python（VLLM_VENDOR 未设）
flag_gems:    5.3.4（重推后，强制重装）✅  j0/log2 已修；3 op 黑名单（lift_fresh/lift_fresh_copy/_to_copy）
NPU device:   ✅ NPU 1                 910B4（NPU 0 被他人占用）
vllm import:  ✅
vllm serve:   ✅  application startup complete（Qwen3-4B TP=1, max-len 2048, mem-util 0.6, enforce-eager）
Inference:    ✅  "The capital of France is" → " Paris. The capital of Germany is Berlin.
                  The capital of Italy is Rome..." 连贯英语；32 token，finish_reason=length，
                  POST /v1/completions 200 OK，无 coreDim/libatb/dtype 错
```

### 待办

1. **`lift_fresh`/`lift_fresh_copy`/`_to_copy` 黑名单对齐 Mac 源码并提 PR** —— **✅ 已提**：
   [PR #361](https://github.com/flagos-ai/vllm-plugin-FL/pull/361)（flagos-ai/vllm-plugin-FL，
   分支 `ascend-blacklist-lift-fresh`→`release-0.2`）：`dispatch/config/ascend.yaml`；
   coreDim=0 标量崩溃规避，回退 torch_npu 无损。根治方向：flag_gems 标量/极小张量 grid 下限保护
2. **ATB `set_env.sh` 烘焙进 base image env** —— **✅ 已提**：两后端分属不同 PR，
   cann9.0.0 = [PR #353](https://github.com/flagos-ai/build-infra/pull/353)
   （`base/ascend-cann9.0.0` 在 CANN 之后 source NNAL/ATB `set_env.sh`）；cann8.5.0 =
   [PR #354](https://github.com/flagos-ai/build-infra/pull/354)（补 NNAL）+
   [PR #355](https://github.com/flagos-ai/build-infra/pull/355)（捕获 NNAL/ATB env 进
   `vendor.sh`）。`ATB_HOME_PATH` / ATB lib path 进 `vendor.sh`，消除运行时手动 source；
   否则 ATB 后端算子（reshape_and_cache/rotary_embedding）在裸 shell 崩溃
3. **flag_gems 5.3.4 重推 v2 镜像刷新** —— **🔄 进行中**：现镜像烘焙旧 wheel，
   须强制重装才可用；全部 17 个 v2 runtime 镜像重建后消除（用户驱动）
4. **ascend `+flagos` wheel 上架** —— **✅ 已上传**：4 个 wheel 已上架 `flagos-pypi-ascend`（用户上传）

**相关提交：** plugin 黑名单已提 **[PR #361](https://github.com/flagos-ai/vllm-plugin-FL/pull/361)**（`ascend-blacklist-lift-fresh`→`release-0.2`，commit baeafde）。wheel 复用 Phase A + 用户上传（无落库）；ATB env 1 处在容器内，base image 待对齐。

### 后续（2026-08-24）：ascend 双后端 0.20.2 全路径 F/T 双编译器 E2E 全 ✅

两个 ascend 后端（cann9.0.0、cann8.5.0）**release-0.2 实测**（不预置黑名单、
不回移植 0.24.0 线）：serve + 推理（Qwen3-4B）F（flagtree）与 T（triton）双路径均 E2E 通过，
64 token 贪婪解码连贯。矩阵 0.20.2(T)/0.20.2(F) 两列由 ⬜ 翻 ✅。

| 后端 | F（flagtree） | T（triton） |
|---|---|---|
| cann9.0.0 | ✅ | ✅ |
| cann8.5.0 | ✅ | ✅ |

相比 §2.8（2026-08-10 仅 F 路径）实测新增一处黑名单，与前 3 处（lift_fresh / lift_fresh_copy /
_to_copy）同落 `dispatch/config/ascend.yaml`（cann8.5.0 / cann9.0.0 共用）：

4. **症状：** 推理崩溃 `pow_scalar`

   **根因：** flag_gems `_ascend/ops/pow.py` 用三个 `tl.constexpr()` **OR 条件**做分支守卫
   （非 `a < b < c`）。**两后端根因不同**：cann8.5.0（flagtree 0.6.0+ascend3.2）F/T 双路径均拒绝；
   cann9.0.0（flagtree 0.6.1+ascend3.5）仅 vendor triton 拒绝，F 路径已修

   **修复：** `flagos_blacklist` 加 `pow_scalar`（回退 torch_npu 无损；8.5.0 遮 F+T、9.0.0
   仅需遮 T），已提 [PR #402](https://github.com/flagos-ai/vllm-plugin-FL/pull/402)
   （`ascend-blacklist-pow-scalar`→`release-0.2`）

**两后端修补差异（`dispatch/config/ascend.yaml` 共用，但根因/作用域不同）：** pow_scalar 黑名单是
**共享条目**，但两后端触发的路径不同——差异源于 **flagtree 版本**：cann8.5.0 用 flagtree
0.6.0+ascend3.2，其仍拒绝 pow.py 的 `tl.constexpr()` OR 条件（F 路径也崩，故黑名单遮 F+T）；
cann9.0.0 用 flagtree 0.6.1+ascend3.5，已修此缺陷（F 路径通过，仅 vendor triton 仍拒绝，黑名单
只需遮 T）。反向的差异是 §2.8 修复 #1 的 j0/log2：那是 flagtree 0.6.1（cann9.0.0）libdevice 缺口，
cann8.5.0 的 flagtree 0.6.0 libdevice 无此问题，故 8.5.0 无需重装 5.3.4（实测其 j0 缺失但 import
不崩）。即：**8.5.0 多修 pow_scalar 的 F 路径、少修 j0/log2；9.0.0 反之。**

NPU 冷启动 JIT 极慢：T 路径首请求 872s（逐 shape 编译 triton/NPU 内核），稳态 0.1~0.2 tok/s，
64 token decode 约 11~15 min。慢≠挂：以 `generation_tokens_total` 增量 + `num_requests_running` 归零
判断完成，勿以客户端 curl 超时误判卡死。

**构建源与上游 PR 追踪（fork 分支 provenance）：** #361 与 #402 是**两个独立分支**，各自只含一半
黑名单（#361 = lift_fresh 系 3 条、#402 = pow_scalar 1 条），0.20.2 ascend 两后端需**四条全齐**。
上游 merge 由 plugin 团队掌控、无法控制，故 wheel 从 fork 上的合成分支构建（`vllm-plugin-wheel.yml`
`plugin_repo` 指 fork、`plugin_ref` 指合成分支 SHA），与其它后端从 fork 打 pre-merge wheel 同一流程。

| 合成分支 commit（构建源） | 上游原始 commit | 上游 PR |
|---|---|---|
| `00cc275` lift_fresh 系 | `baeafde` | [vllm-plugin-FL#361](https://github.com/flagos-ai/vllm-plugin-FL/pull/361) |
| `05f246b` pow_scalar | `13a91ef` | [vllm-plugin-FL#402](https://github.com/flagos-ai/vllm-plugin-FL/pull/402) |
| `2b6b635` pow_scalar 注释修正 | `e084195` | [vllm-plugin-FL#402](https://github.com/flagos-ai/vllm-plugin-FL/pull/402) |

合成分支 = `tengqm/vllm-plugin-FL:ascend-blacklist-release-0.2` @ `2b6b635cd93c5578ba945cf935f7c7f7e1d5d882`
（基于 `release-0.2` @ `825c1cd` cherry-pick 三笔，内容与上游逐字节一致，SHA 因 cherry-pick 重写
committer/date/parent 而不同）。wheel 版本串 `0.2.0+g2b6b635.d20260824` 把构建 SHA 烙进元数据，app 镜像
安装 pin 带进 image_tag，status_matrix 记 image_tag → 版本串 → 上游 PR，追踪链闭合。**#361/#402 merge 进
上游 release-0.2 后，用上游新 HEAD 重打 wheel（内容逐字节相同，仅版本串 SHA 换上游值），届时删除本表。**

**PR 追踪约定（6 个 app × 17 后端 × F/T 双路径，PR 数量会很多）：** 持久源 = status_matrix 的
`backends.<name>.prs:` 字段（结构化，已被 enflame/kunlunxin/sunrise 使用，记录「该后端 image 依赖的
上游 PR URL」），merge 后仍保留；临时源 = 本表这类 fork-SHA → PR 映射，仅在 PR 未 merge 期间存在、
merge + 重建后即删。**每后端跑通时：上游 PR 进 `prs:`（永久）、fork 合成分支映射进 report「后续」（临时）。**
