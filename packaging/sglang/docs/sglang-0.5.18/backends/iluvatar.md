# sglang 0.5.18 — Iluvatar CoreX 验证记录

> **两个变体都已验证（F/T 双路径）**：4.5.0（§1–§5，2026-09-10）与
> 4.4.0（§6，2026-09-12）。corex 的 torch 是 CUDA-alias 构建
> （`torch.version.cuda` 有值），sglang 的 `is_cuda()` 因此为真、走 CUDA 分支，
> 但该平台既无 NVIDIA 设备、也没有那些分支期望的 NVIDIA 专属包。4.5.0 的阻塞
> 全部来自这一错位；4.4.0 另有一层 torch 版本落差，见 §6。

## 1. 环境

| 项 | 值 |
|---|---|
| 节点 | ix23（Iluvatar BI-V150，6 卡，device 4）|
| 镜像 | `flagos-runtime-iluvatar-corex4.5.0:2.1.2` |
| Python | 3.12 |
| torch | 2.10.0+corex.4.5.0.20260804 |
| flagtree | 0.6.1+iluvatar3.6（F 路径，内 triton 3.6）|
| vendor triton | 3.2.0+corex.4.5.0.20260804（T 路径）|
| flag_gems | 5.3.5（双路径共享）|
| sglang | 0.5.18+flagos |
| sgl-kernel-shim | 0.5.18 |
| flashinfer-shim | 0.1.0（本线新增，见 §3）|
| sglang-plugin-FL | `exp/0.5.18-iluvatar` |
| 模型 | Qwen3-4B（`/data/models/Qwen/Qwen3-4B`；节点无 0.6B）|

设备实况：`torch.cuda.get_device_capability()` 返回 **(7, 1)** —— 这是 corex 的
CUDA 兼容性标识，不是 NVIDIA SM 等级；`torch.cuda` 本身可用（count=1）。

## 2. 修复链

六个阻塞，前三个是"从零安装起不来"，后三个是"起来后跑不动"。

| # | 阻塞 | 归属 |
|---|---|---|
| 1 | `compressed_tensors` 缺失：0.5.18 从 quantization 包无条件 import，`ServerArgs → model_config` 在加载任何模型前就走到 | build-infra `deps_app` pin |
| 2 | Step 4 插件 clone 失败：容器内无出网代理（`docker exec` 不继承环境）| build-infra verify 脚本中继节点代理 |
| 3 | flashinfer 不存在但 `is_cuda()` 为真 → 三处模块级 import 崩 | 插件仓库（on-disk stub）|
| 4 | sglang 硬断言 `only supports sm75 and above` | 插件仓库 |
| 5 | `clamp_position` 走 nvcc JIT（corex 无 nvcc）| 插件仓库 |
| 6 | vendor triton 3.2 缺 PDL 内建，AST 预扫描即报错 | 插件仓库 |

### 2.1 flashinfer 是 on-disk 包，不是插件内 stub（#3）

**为什么不能在插件里打补丁**：sglang 的 scheduler 跑在 **spawn 子进程**里，该进程
在 module-import 阶段就 `import sglang.srt.managers.scheduler` → quantization →
fp8 → flashinfer，**早于任何插件加载**。节点实测：插件装上后裸跑
`python3 -c "import sglang.srt.managers.scheduler"` 依然 `ModuleNotFoundError`，
引擎随后以 "Rank 0 scheduler died during initialization" 收场。

结论 = 名字必须能从磁盘解析，与 ascend 的 `sgl_kernel_npu` stub 同一判断。
新增 `addon/flashinfer-shim`（`flashinfer_shim-0.1.0-py3-none-any.whl`）：

- 只提供 sglang 在 `if is_cuda` 下 import 的白名单符号；
- 白名单外的名字抛 `AttributeError` —— 这样 sglang 里大量 `hasattr(...)` 能力
  探测仍给出诚实答案，不会被骗进 CUDA 分支；
- 桩函数**被调用即抛 RuntimeError**，绝不静默算错；
- import 时钉住 `SGLANG_IS_FLASHINFER_AVAILABLE=false`（stub 让
  `find_spec` 成功，而该开关决定 sampling/attention 后端选择）。

发布范围：只上传到 `deps_app` 点名要它的厂商索引（当前仅 iluvatar），
**绝不允许覆盖真 flashinfer**。

> 评估过直接用 PyPI 的 `flashinfer_python-0.6.18`：纯 Python 但那半包压在
> NVIDIA 上 —— sglang 要的 `cudnn_batch_prefill_with_kv_cache` 经
> `flashinfer.prefill` → `flashinfer.cudnn.prefill` → 裸 `import cudnn`
> (nvidia-cudnn-frontend)；元数据还拖 7 个 NVIDIA 专属依赖，且 `torch`/`numpy`
> 未 pin（可能把 numpy 顶到 2.x）。corex 上这些 kernel 跑不了、开关仍须关，
> 收益为零。故不采用。

### 2.2 sm75 断言（#4）

`load_model_utils.maybe_downgrade_dtype_for_legacy_gpu()` 读
`torch.cuda.get_device_capability()`，低于 sm80 时降 dtype 到 float16，随后
minor < 5 即抛错。iluvatar 报 (7, 1) → 每次 serve 在
`ModelRunner.load_model()` 即死。插件重绑为 corex 版：**保留 float16 降级**
（BI-V150 无 bfloat16，dtype 必须降），只去掉 NVIDIA 的 SM 下限。

### 2.3 clamp_position JIT（#5）

`forward_batch_info` 在 import 期二选一：`is_cuda() or is_hip()` → nvcc JIT 版；
否则 `_clamp_position_native`。corex 为真故选中 JIT 版，而 corex 无 nvcc：

```
RuntimeError: Failed to build JIT module sgl_kernel_jit_clamp_position_int64_t
in /root/.cache/sglang/jit/sm71/...
```

该函数由 `ForwardBatch.init_new` 每 batch 调用一次，首个请求即崩。插件把模块全局
重绑到 sglang 自带的 `_clamp_position_native`（与 kunlunxin 补丁同一接缝；
0.5.18 上 kunlunxin 补丁里另一处 overlap 符号已不存在）。

### 2.4 vendor triton 缺 PDL 内建（#6）

sglang 的 attention kernel 在 `if USE_PDL:` 下引用
`tl.extra.cuda.gdc_wait()` / `gdc_launch_dependents()`（triton 3.3+ 引入）。
corex 的 vendor triton 是 **3.2**，且其 JIT 在 AST 预扫描阶段解析**整段函数体的
所有属性**，因此即使 `USE_PDL=False`、分支不执行，编译仍中止：

```
File "/opt/triton/triton/runtime/jit.py", line 307, in visit_Attribute
    ret = getattr(lhs, node.attr)
AttributeError: module 'triton.language.extra.cuda' has no attribute 'gdc_launch_dependents'
```

插件在缺属性时补 no-op。`USE_PDL` 在 corex 恒为 False（PDL 是 NVIDIA Hopper+
特性，`is_arch_support_pdl()` 返回 False，见 §3），故调用永不执行。F 路径
（flagtree triton 3.6）有这些内建，不受影响 —— 这是双路径必须分开跑的原因。

节点上以最小 kernel 先行验证：注入前属性不存在 → 注入后同一 kernel `COMPILE_OK`。

### 2.5 零 sgl-kernel 路线的第一处真调用（#3 附带）

`triton_backend` 调用 `sgl_kernel.utils.is_arch_support_pdl()` 并**把返回值当
constexpr 传进 kernel**。shim 的 `_Dummy` 在这里不是 import 面问题而是真值问题，
报错出现在很远的地方：

```
TypeError: sequence item 13: expected str instance, _Dummy found
    (triton 的 constants 哈希)
```

shim 生成器（`addon/sgl-kernel-shim/generate.py`）现为该符号发真实现，返回
`False` —— PDL 是 NVIDIA Hopper+ 特性，对任何非 NVIDIA 后端这都是诚实答案。

## 3. E2E 验证（F/T 双路径）

判据：serve ready（log 出现 "The server is fired up and ready to roll"）后
3× chat/completions HTTP 200 + completion_tokens>0 + sampling_backend=pytorch
（经 /server_info 确认）。模型 Qwen3-4B，max_tokens 144。安装后矩阵逐项不变
（torch 2.10.0+corex / flag_gems 5.3.5 / numpy 1.26.4，triton 在默认解释器下
MISSING 属正常）。

| 路径 | 编译器 | 结果 |
|---|---|---|
| F | flagtree 0.6.1+iluvatar3.6（triton 3.6）| ✅ 3/3 全过，ct=144，sampling_backend=pytorch |
| T | vendor triton 3.2.0+corex.4.5.0.20260804 | ✅ 3/3 全过，ct=144，sampling_backend=pytorch |

两路径均在同一插件分支头（`0.1.dev1+g201484665`）上验证。

## 4. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | flagtree 的 iluvatar overlay 在生产路径 import pytest：`triton/spec/iluvatar/triton/testing.py::nvsmi` → `from triton._internal_testing import is_corex`，而该模块模块级 `import pytest`；触发链是 flag_gems `_iluvatar` mm/addmm 的 `perf_model` 在 autotune 剪枝时估值 | 上游 issue（FlagTree #1142）+ `deps_app` 显式装 pytest，待上游修复后移除 |
| 2 | 同栈 vendor triton 在同一函数里**本地定义** `is_corex()`，不碰 `_internal_testing` —— 说明这是 flagtree spec overlay 的打包缺陷，非调用方问题 | 作为 #1142 的对照证据 |
| 3 | 堡垒机对 `10.31.28.2x` 各挂两个同名资产（`n23`/`tianshu-n23`），非交互 exec 被拒；只有 2 号资产网络可达 | 运维侧注意；本轮用应答菜单的 expect 助手绕过 |
| 4 | ix23 只能经节点代理出网，`docker exec` 不继承环境 | verify 脚本按需中继 `http_proxy`/`https_proxy`/`no_proxy`（#2）|

## 5. 遗留（4.5.0）

- 插件分支 `exp/0.5.18-iluvatar` 待合入 `exp/0.5.18`；正式 wheel 由
  `sglang-plugin-wheel` workflow 从该分支产出。
- FlagTree #1142 修复后，从 `deps_app` 移除 `pytest`。

## 6. CoreX 4.4.0 详细记录（2026-09-12）

> **验证通过（F/T 双路径）**。4.5.0 的六个阻塞在这里以同样方式成立，另加两个
> 4.4.0 独有的落差：SDK 钉死的 torch 是 **2.7.1**，低于 sglang 0.5.18 实际要求
> 的 2.8；vendor triton 是 **3.1.0**，比 4.5.0 的 3.2 更旧。修复落在插件分支
> `exp/0.5.18-iluvatar-corex440`（PR #105）。

### 6.1 环境

| 项 | 值 |
|---|---|
| 节点 | ix15（Iluvatar BI-V150，corex 4.4.0）|
| 镜像 | `flagos-runtime-iluvatar-corex4.4.0:2.1.2` |
| Python / torch | 3.12 / **2.7.1+corex.4.4.0** |
| flagtree | 0.6.1+iluvatar3.6（F 路径，内 triton 3.6.0）|
| vendor triton | **3.1.0+corex.4.4.0**（T 路径）|
| flag_gems | 5.3.5（双路径共享）|
| sglang / 插件 | 0.5.18+flagos / `exp/0.5.18-iluvatar-corex440` @ `4d44a24cd` |
| 模型 | Qwen3-4B |

设备 capability 答 **(7, 1)**，与 4.5.0 同（corex 的 CUDA 兼容标识）。

### 6.2 4.4.0 独有的两个阻塞

**#7 torch 2.7 缺 sglang 0.5.18 假定存在的两处 torch 表面。** 两处都在 Qwen3
启动路径上、都是模块级 import、都在 2.8 才有：

| 缺口 | 调用点 | torch 2.7 有 |
|---|---|---|
| `torch.cuda.memory._cuda_beginAllocateCurrentThreadToPool` / `_cuda_endAllocateToPool` | `pynccl_allocator` | 同两个操作的旧拼写 `_cuda_beginAllocateToPool` / `_cuda_endAllocateCurrentStreamToPool` |
| `torch.distributed._symmetric_memory`（import 直接失败：无 `_C._distributed_c10d._SymmetricMemory`）| `logits_processor` → `triton_symm_mem_ag` | 无 —— 它是 NVLink 多播 all-gather |

第一处是 **torch 的改名而非不同操作**：`pynccl_allocator` 自己就按
`after_2_8_0` 在两种拼写之间选（`torch._C._cuda_endAllocateToPool` vs
`_cuda_endAllocateCurrentStreamToPool`）。第二处本平台永不执行 —— sglang 自己的
`is_symmetric_memory_enabled()` 读 `comm.enable_symm_mem`，这里恒为 False。

**为什么是 on-disk 包而不是插件补丁**：scheduler 跑在 **spawn 子进程**里，该进程
在 module-import 阶段就 `import sglang.srt.managers.scheduler`（连带这两处），
**早于任何插件加载** —— 与 §2.1 flashinfer 同一判断。实测：装上插件后裸跑
`python3 -c "import sglang.srt.managers.scheduler"` 依然 ImportError。

新增插件 addon `addon/torch-compat/`，以 **`sitecustomize`** 分发（`site` 在解释器
启动时导入，子进程同样生效）。它的 hook 只包住 `sglang` 包的 import，因此不 import
sglang 的解释器零成本；两个补丁在 torch ≥ 2.8 上都是 no-op。
`torch-compat-shim==0.1.0` 经 `deps_app.sglang0.5.18` 只装到 4.4.0。

**#8 vendor triton 3.1.0 对 PDL no-op 断言。** §2.4 给 vendor triton 注入的 PDL
no-op 在 3.2 上够用，在 3.1.0 上被 triton 自己的依赖扫描断言拦住：

```
AssertionError: Function "_noop" is being called from a Triton function but is
not a Triton function itself. Decorate it with @triton.jit to fix this
```

`visit_Call` 的判据是 `func.__module__.startswith("triton")`；3.2 跑同一个判据但
**只测不断言**，所以这个 4.5.0 从未暴露、只在 T 路径上出问题的缺陷直到 4.4.0 才
显形。修复 = 注入的 no-op 声明自己属于它被装进的那个命名空间。

### 6.3 E2E 验证

判据同 §3；F 与 T 同一份配置，唯一变量是编译器，两路径都在插件头 `4d44a24cd`。

| 路径 | 编译器 | 结果 |
|---|---|---|
| F | flagtree 0.6.1+iluvatar3.6（triton 3.6.0）| ✅ ready ~105s，3/3，ct=144 |
| T | vendor triton 3.1.0+corex.4.4.0 | ✅ ready ~265s，3/3，ct=144 |

安装后依赖矩阵（torch 2.7.1+corex.4.4.0 / flag_gems 5.3.5 / numpy 1.26.4）逐项
不变；`sampling_backend=pytorch` 两侧一致。

### 6.3a app 镜像（走正式链路）

插件分支的 wheel 由 `sglang-plugin-wheel` workflow 在**本后端自己的 runtime 镜像**
内从该分支构建，上传 `flagos-pypi-iluvatar`
（`sglang_fl-0.1.dev1+g4d44a24cd-py3-none-any.whl`；同一次运行也发布本后端
`deps_app` 点名的 `torch-compat-shim`），再走 changelog 门禁 → app 镜像构建 →
**镜像内 serve E2E** → push：

```
harbor.baai.ac.cn/flagos-app/sglang0.5.18-iluvatar-corex4.4.0:2.1.2-0.1.dev1_g4d44a24cd
digest sha256:f3d95abf5f6ebad1c110a6b61f256d61f8c028db6730bf0e29b602ead2e9886c
```

镜像内验证（`--app-image` 模式）：关键包矩阵与 runtime 一致、`sglang + sgl_kernel +
sglang_fl` 可导入、serve ready ~100s、3/3 ct=144。镜像标签
`flagos.plugin=0.1.dev1+g4d44a24cd`，pull 回来的 digest 与 push 记录一致。

### 6.4 与 vllm 线结论的关系

vllm 线在 4.4.0 上判 **T 不可交付**（vendor corex triton 3.1.0 存在不可修复缺陷，
[vllm §14.4](../../../vllm/docs/vllm-0.24.0/backends/iluvatar.md)）。sglang 这边
T 路径**通过** —— 差别在于本轮 T 的失败点不在厂商工具链，而在我们自己注入的
no-op 上（#8）。这不推翻 vllm 的结论（那是 vllm 侧算子路径的实证），但说明
"4.4.0 的 triton 一律不可用"不是可以外推的前提：**同一个 SDK 上，sglang 的 T
路径是可交付的。**

### 6.5 坑清单补充（4.4.0）

| # | 坑 | 处置 |
|---|---|---|
| 5 | 4.4.0 的 JIT qknorm / kvcache 内核在 corex 的 nvcc 10.2 下编译失败（`cannot find cuda_0.o`），走谓词的 except 分支回落 native | 与 kunlunxin 恰好相反：那里 nvcc 编得出来、启动才崩；这里编不出来反而是安全的。两者都说明 `can_use_*` 谓词不能当作能力真相 |
| 6 | 插件 wheel 与 addon 的分工：`torch-compat-shim` 是**独立 addon**，不并入 flashinfer-shim —— 前者是 torch 版本落差，后者是缺失的包，坏在一起会让"谁在为哪件事负责"重新变模糊 | 各自独立打包、独立 `deps_app` 计入 |

### 6.6 遗留（4.4.0）

- 插件 PR #105 待合入 `exp/0.5.18`（它是 #102 的堆叠 PR，base 指向
  `exp/0.5.18-iluvatar`；#102 合入后需把 base 改回 `exp/0.5.18`）。
- `torch-compat-shim` 只为 torch < 2.8 的平台存在；4.4.0 SDK 若升 torch，应从
  `deps_app` 移除（补丁本身届时自动 no-op，但包不该继续装）。
