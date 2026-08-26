# 昆仑芯 P800 XPU — Triton 编译器 attention 内核编译问题（编译器团队 hand-off）

**日期：** 2026-08-11　**报告人：** FlagOS 集成验证

**硬件：** 昆仑芯 P800 OAM　**XRE：** 5.37.1（driver 5.37.1.0）　**目标 arch：** `xpu_arch=3` / xpu3

**场景：** vLLM 0.20.2（empty build）+ vllm-plugin-FL + flag_gems 5.3.4（`_kunlunxin` 后端），serve Qwen3-4B 全链路推理

**torch：** 2.9.0+cu129（stock，CUDA-ABI 兼容）+ `torch_xmlir`

---

## TL;DR

在同一颗 P800 上，用**两套厂商 XPU triton 编译器**、跑**两个不同来源的 attention 内核**，共命中**三处不同的编译失败**。
三者全部是 **attention 类内核（flash 式：循环携带指针 + 在线 softmax 状态）无法编译到底**，而非某个单一坏内核。
GEMM / rms_norm / rotary / silu 等非 attention 内核均正常。

由于这颗芯片上 vLLM 的所有 attention 计算后端都走 triton（无纯 torch-eager attention 后端可退），此问题**在应用/插件层无法绕过**，需编译器侧修复。

---

## 两套编译器的确切版本

| 编译器 | `triton.__version__`（仅 shim 值） | 真实包版本 | 路径 |
|--------|-----------------------------------|-----------|------|
| **FlagTree**（默认/主推） | `3.6.0` | **`flagtree 0.6.1+xpu3.6`**（`pip show flagtree`） | `/opt/flagtree` |
| vendor triton（备选） | `3.0.0` | **`triton 3.0.0+a48aedef`**（dist-info） | `/opt/triton` |

- 两套共用底层后端：**XTDK-llvm19-ubuntu2004_x86_64**（LLVM 19）。
- 切换方式：容器内 `compiler` bash 函数切 `PYTHONPATH`。
- 上游 triton 无 XPU/SDNN 后端，故不存在"真·原生"triton 对照。

---

## 三处失败

### 问题 1 — FlagTree 0.6.1+xpu3.6：`TritonSDNNLegalize` 无法合法化 flash 内核

- **内核：** flag_gems `_kunlunxin` flash（`flash_kernel.py:1212`）
- **时机：** profile / warmup 期（首次编译）
- **失败 pass：** `TritonSDNNLegalize`
- **原始报错：**
  ```
  flag_gems/runtime/backend/_kunlunxin/ops/flash_kernel.py:1212:0: error:
    Failures have been detected while processing an MLIR pass pipeline
  flash_kernel.py:1212:0: note: Pipeline failed while executing
    [`TritonSDNNLegalize` on 'builtin.module' operation]:
    reproducer generated at `std::errs, please share the reproducer above with Triton project.`
  ```
- **tuning 无关：** `num_stages` 3→1、`BLOCK_M` 128→64 报错完全一致 → 非资源问题。

### 问题 2 — FlagTree 0.6.1+xpu3.6：`TritonSDNNCombineBefore` 无法处理循环指针状态

- **内核：** vLLM 自带 `unified_attention`（`triton_unified_attention.py`，非 flag_gems）
- **时机：** 推理期（首个真实请求现场编译）
- **失败 pass：** `TritonSDNNCombineBefore`
- **原始报错：**
  ```
  vllm/v1/attention/ops/triton_unified_attention.py:232:28: error:
    Rewrite for-op failed. Could not find PtrState returned by the loop.
  triton_unified_attention.py:58:0: note: Pipeline failed while executing
    [`TritonSDNNCombineBefore` on 'builtin.module' operation]:
    reproducer generated at `std::errs, please share the reproducer above with Triton project.`
  ```
- 关键诊断：**"Could not find PtrState returned by the loop"** —— pass 无法追踪 attention 内层循环里携带的指针状态。这正是 flash 式 attention 的核心结构。

### 问题 3 — vendor triton 3.0.0+a48aedef：XTDK LLVM19 后端空 SetVector 断言 abort

- **内核：** flag_gems `_kunlunxin` flash（同问题 1 的内核）
- **时机：** 前端 MLIR pass **通过了**（server 起来、`/health` 200、KV cache 分配完成），崩在**首个真实 shape 推理请求**的后端 codegen
- **失败点：** XTDK LLVM19 后端，`SetVector::front()` 对空集断言
- **原始报错：**
  ```
  Core: .../_deps/xtdk/xtdk-llvm19-ubuntu2004_x86_64/include/llvm/ADT/SetVector.h:144:
    const value_type& llvm::SetVector<T, Vector, Set, N>::front() const
    [with T = mlir::Attribute; ...]:
    Assertion `!empty() && "Cannot call front() on empty SetVector!"' failed.
  ```
- C++ 断言直接 abort 整个 EngineCore 进程（不是 Python 异常，无法 catch）。

---

## 假象说明：日志里的 "OutOfResources / SRAM = 0" 不是真的资源不足

FlagTree 侧（问题 1、2）最终都被 `backends/xpu/compiler.py:367` 兜底包成：

```python
raise OutOfResources(0, 0, f"uni_sram {e}")
```

所以上层日志会显示 `triton.runtime.errors.OutOfResources: out of resource: uni_sram ... Required: 0, Hardware limit: 0. Reducing block sizes or num_stages may help.`

**"Required: 0, Hardware limit: 0" 是无意义的占位值** —— 它是把任意 MLIR pass 异常吞掉后统一换成的假象，
并非真的 SRAM 溢出。真实根因是上面 note 行里的 pass 失败。调小 block / num_stages 无效（已验证）。

---

## 完整 pass pipeline（xpu_arch=3，供定位）

FlagTree XPU 后端实际执行的 pass 链（从日志 dump）：

```
builtin.module(
  triton-loop-aware-cse,
  strip-all-ir{xpu_arch=3},
  triton-convert-type{mode=0 xpu_arch=3},
  triton-to-linalg-experimental{xpu_arch=3},
  triton-loop-aware-cse,
  linalg-to-tritonsdnn{xpu_arch=3},
  triton-loop-aware-cse,
  tritonsdnn-legalize{xpu_arch=3},          ← 问题 1 崩这里
  tritonsdnn-combine-before{xpu_arch=3},    ← 问题 2 崩这里
  func.func(tritonsdnn-bufferize{xpu_arch=3}),
  tritonsdnn-combine{xpu_arch=3},
  tritonsdnn-ew-act-table,
  tritonsdnn-loop-grid,
  tritonsdnn-pipeline,
  tritonsdnn-multi-buffer{num_stages=1 xpu_arch=3},
  symbol-dce, canonicalize{...}, cse)
```

---

## 汇总

| # | 内核 | 编译器 | 崩溃阶段 | 失败 pass / 位置 | 时机 |
|---|------|--------|----------|------------------|------|
| 1 | flag_gems `_kunlunxin` flash | FlagTree 0.6.1+xpu3.6 | MLIR 前端 pass | `TritonSDNNLegalize` | profile |
| 2 | vLLM `unified_attention` | FlagTree 0.6.1+xpu3.6 | MLIR 前端 pass | `TritonSDNNCombineBefore`（"Could not find PtrState returned by the loop"） | 推理 |
| 3 | flag_gems `_kunlunxin` flash | triton 3.0.0+a48aedef | XTDK LLVM19 后端 codegen | `SetVector::front()` 空集断言 | 推理 |

---

## 归纳与请求

**根本问题不是某一个坏内核**：两套编译器、两个不同来源的 attention 内核，三处不同失败，
共同点都是"attention 类内核（循环携带指针 + 在线 softmax 状态）无法编译到底"。

- **FlagTree** 卡在前端 MLIR pass（`TritonSDNNLegalize` / `TritonSDNNCombineBefore` 对循环内指针状态处理失败）；
- **triton 3.0.0** 前端过了，却卡在共用的 **XTDK-LLVM19** 后端 codegen（空 `SetVector` 断言）。

**请求编译器团队：**
1. **问题 1、2（FlagTree）** 优先：SDNN pass 链（`tritonsdnn-legalize` / `tritonsdnn-combine-before`）
2. 需支持 attention 内层循环携带的指针状态（PtrState）。这是主推路径的硬阻塞。
3. **问题 3（triton 3.0.0）**：XTDK-LLVM19 后端 `SetVector::front()` 空集断言需加防护 / 定位为何该集合为空。
4. 每处失败 triton 都提示 `reproducer generated at std::errs` —— 如需，我们可回放并提供 MLIR reproducer（详见下方 2026-08-21 补充，reproducer 已随日志留档）。

**验证环境可保留：** 容器 `vllm-verify-kunlunxin` 保持现状，可随时复现三处失败并抓 reproducer。

---

## 2026-08-21 补充：SDNN objects 版本无关性 + 绕过证伪（实验闭环）

为排除"SDNN objects 版本回归"嫌疑并验证应用层是否有绕过路径，做了两轮实验，结论：
**问题 1、2 与 SDNN objects 版本无关；应用/插件层无绕过路径，必须编译器侧修复。**

### 实验 1 — SDNN objects 回退重编（wheel 级差分）

- 构建链：`flagos-runtime-kunlunxin-xre5.37.1:2.1.2`，git HEAD + SDNN objects 回退 `v0.3.6.2.0`（xpu.py pin）
- + `MLIRTargetLLVMIRImport` 链接修复 → wheel `flagtree-0.6.1+xpu3.6.oldtest`
  + （libtriton.so 849MB，与旧 wheel 同族；v7 系 708MB 为异族）。
- 二进制差分：`init_triton_sdnn_passes_transform` 守卫恢复（`movzbl 0x40(%rbx)` → `test` → `je` 错误路径，
- 字节级修复 v7 的 NULL 解引用）；两代 SDNN objects 均为 pybind11 3.x 时代（`_pybind11_internals_v11`），守卫差异 = vendor 3.x codegen 回归。
- 效果：**pybind11 崩溃（`xpu.is_sdnn_kernel` / `init_triton_sdnn_passes_transform` 空指针）全部消除**——
- imports、dispatch manager、rms_norm/rotary/silu 全 dispatch 成功。
- 但两个 attention 路径原样失败，报错与修复前逐字一致：
  **问题 1**（flag_gems `flash_kernel.py:1212` → `TritonSDNNLegalize`）、
  **问题 2**（vLLM `triton_unified_attention.py:232` → `TritonSDNNCombineBefore`
  "Could not find PtrState returned by the loop"）。
- **结论：原问题 1、2 与 SDNN objects 版本无关。** wheel 级重编只修 pybind11 崩溃这一件事。

### 实验 2 — `is_sdnn=False` 强制绕过（pipeline 切换）

- 补丁：`compiler.py:225` 强制 `metadata["is_sdnn"] = False` → attention 内核路由进 tritonxpu **KT_CLUSTER** pipeline
  （rms_norm/rotary/gemm 已验证可行的路径，reproducer pipeline 字符串证实无任何 SDNN pass）。
- 结果：两个 attention 内核（`flash_kernel.py:1212` 与 `triton_unified_attention.py:58`）
  在 KT_CLUSTER pipeline 同样失败，挂在**第一个** pass `ConvertTritonToTritonXPU`。
- **结论：attention 内核在 SDNN 与 KT_CLUSTER 两条 pipeline 均编译失败**
  （SDNN 路径挂 SDNN pass，cluster 路径挂基础 lowering），非 pass 特有 → 应用层（改 routing / 换 attention 后端）**无法绕过**，与文档开头"此问题在应用/插件层无法绕过"的判定一致并进一步坐实。

- 结论方向：**FlagTree xpu backend 的 lowering（SDNN pass 链 + 基础 lowering 对循环携带指针状态的支持）为修复落点**，
  属编译器团队工作；集成侧在 vLLM 自带 backends 范围内无 workaround——厂商已于插件层提供替代路径，见下节。

---

## 2026-08-21 补充（续）：厂商插件层修复 —— vllm-plugin-FL PR #268

**厂商立场：该修补没有问题。** vllm-plugin-FL PR #268（"Support kunlunxin
backend"，2026-08-19 合并）新增完整 kunlunxin vendor backend，kunlunxin
推理路径以它为官方实现；attention 不再经过 Triton 编译器：

- **attention**：`xtorch_ops.prefill_attention` / `decode_paged_attention`
  （替代 flag_gems flash 与 vLLM unified_attention 两个 Triton 内核）
- **KV cache**：`xtorch_ops.reshape_and_cache` / `reshape_and_cache_flash`
  （HND 布局，与本文档场景一致）
- **其余算子**：rms_norm / rotary_embedding / swiglu / MoE / FLA-GDN 均改用
  `xtorch_ops` 或插件内实现；配套 8 处 monkey patch（slot_mapping 改 numpy
  计算、替换 `_forward_core` 等）
- **验证**（据厂商验证文档，日期 20260730；TP=4 说法有出入，以文档为准）：
  Qwen3.6-27B / Qwen3.6-35B-A3B / Qwen3-8B 三个模型，TP=1，block-size 128，
  均设 `USE_RESHAPE_AND_CACHE_FLASH=1`：
  - Qwen3.6-27B：服务无法启动（卡启动初始化，>10h）
  - Qwen3.6-35B-A3B：服务无法启动
  - Qwen3-8B：服务可启动，但推理输出乱码（当时 flag 已设置）
  - **厂商后续澄清**：`USE_RESHAPE_AND_CACHE_FLASH=1` 可解决
    Qwen3-4B（本任务验证模型）的乱码问题——该结论晚于 7/30 文档，
    文档本身仅记录三模型失败状态
- **验证环境差异（厂商 vs 我们）**：厂商 = XTDK **llvm22** + driver
  5.0.21.43 + FlagGems 5.0.0 + flagtree 0.6.1a1 + sdnn-objects
  v0.3.6.2.0；我们 = **llvm19** + driver 5.37.1 + FlagGems 5.3.4。
  sdnn-objects v0.3.6.2.0 与本任务 A1 重编回退版本一致
- **依赖**：插件版本需含 #268；`xtorch_ops` 随 FlagCX 工具链提供，
  需 `FLAGCX_PATH` 指向其目录

**与本文档前文的关系：**

- 三处 Triton attention 编译失败（问题 1/2/3）依然成立、复现方式不变；厂商方案
  是在应用层以新增 native backend 整体替换 attention 内核，前文"应用层无法绕过"
  仅指 vLLM 自带 backends。
- 若 kunlunxin 目标是推理可用性，以 #268 为准（厂商立场：修补无问题），
  Qwen3-4B 乱码按厂商说明设 `USE_RESHAPE_AND_CACHE_FLASH=1` 解决；若仍要
  修复 Triton 编译本身（FlagTree SDNN pass 链与基础 lowering 对循环携带
  PtrState 的支持），前文请求与复现要点不变。
- **待办**：本任务尚未跑 #268 路径（缺含 #268 的插件、xtorch_ops、FlagCX），
  乱码修复结论需在该路径上以 Qwen3-4B 复验。

---

## 附：复现要点（供编译器团队自查）

- 镜像/容器：`vllm-verify-kunlunxin`（节点 `kunlunxin`）
- 切编译器：容器内 `compiler flagtree` / `compiler triton`（切 PYTHONPATH）
- 问题 3 前置环境坑：vendor triton 3.0.0 `import triton` 会 eager 加载 AMD 后端，
  需 `libz3.so.4`（离线 apt 装不到，已从宿主 snapshot 拷入 `/usr/lib/x86_64-linux-gnu/` + `ldconfig`）
- serve 命令：`vllm serve /data/models/Qwen3-4B --tensor-parallel-size 1
  --max-model-len 4096 --enforce-eager --gpu-memory-utilization 0.6 --trust-remote-code`
- 触发问题 1：`VLLM_FL_USE_FLAGGEMS_ATTN=1` + FlagTree（profile 期即崩）
- 触发问题 2：不设 `VLLM_FL_USE_FLAGGEMS_ATTN` + FlagTree（回落 vLLM 自带 triton attn，首个请求崩）
- 触发问题 3：`VLLM_FL_USE_FLAGGEMS_ATTN=1` + `compiler triton`（启动成功，首个请求崩）

---

## 更新（2026-08-23）：0.20.2 已被插件层修复绕开，双编译器 E2E 通过

上述三处编译失败在 **vLLM 0.20.2 线已不构成阻塞**，0.20.2 双编译器路径均 E2E
通过（FlagTree 7/7、triton 3.6.0 3/3，serve + 推理连贯，详见
[vllm-0.20.2/backends/kunlunxin.md](vllm-0.20.2/backends/kunlunxin.md)）。两条绕过路径：

1. **厂商插件层 PR #268**（vllm-plugin-FL）：新增 xtorch_ops 原生 attention
   backend，attention 不再走 Triton 编译，三处失败一并绕开。
2. **triton 3.6.0 升级（#469）**：`/opt/triton` 由 3.0.0 升到 3.6.0
   （vendor wheel 3.6.0+gitcd2d6c1b），问题 3 的 XTDK LLVM19 空 SetVector
   断言在升级后不再出现（3.0.0 另缺 libz3.so.4 的问题也随之解除）。

本文所述编译器侧修复请求仍可作为长期建议保留（FlagTree SDNN pass 链对循环内
指针状态的支持、XTDK 后端空 SetVector 断言防护），但对 0.20.2 交付已非阻塞。
