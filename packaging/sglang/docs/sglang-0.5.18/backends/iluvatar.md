# sglang 0.5.18 — Iluvatar CoreX 4.5.0 验证记录

> **2026-09-10 验证通过（F/T 双路径）**。corex 的 torch 是 CUDA-alias 构建
> （`torch.version.cuda` 有值），sglang 的 `is_cuda()` 因此为真、走 CUDA 分支，
> 但该平台既无 NVIDIA 设备、也没有那些分支期望的 NVIDIA 专属包。本轮阻塞全部
> 来自这一错位，修复落在 sglang-plugin-FL 分支 `exp/0.5.18-iluvatar`。

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

## 5. 遗留

- 插件分支 `exp/0.5.18-iluvatar` 待合入 `exp/0.5.18`；正式 wheel 由
  `sglang-plugin-wheel` workflow 从该分支产出。
- FlagTree #1142 修复后，从 `deps_app` 移除 `pytest`。
- 4.4.0 未验证（torch 2.7.1，工具链更旧；vllm 线在该栈上是负结果）。
