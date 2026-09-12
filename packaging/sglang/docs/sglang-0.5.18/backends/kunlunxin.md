# sglang 0.5.18 — Kunlunxin XRE 5.37.1 验证记录

> **2026-09-12 验证通过（F/T 双路径）**。此栈的 torch 是 CUDA-alias 构建
> （`torch.cuda.get_device_capability()` 返回 `(8, 6)`，`get_device_name()` 返回
> `GPU`），sglang 的 `is_cuda()` 因此为真、全走 CUDA 分支。本轮五个阻塞中三个来自
> 这一错位，两个来自 0.5.18 的 API 漂移；修复全部落在 sglang-plugin-FL PR #104
> （分支 `exp/0.5.18-kunlunxin`）。

## 1. 环境

| 项 | 值 |
|---|---|
| 节点 | kunlunxin（P800 OAM × 8，device 2）|
| 镜像 | `flagos-runtime-kunlunxin-xre5.37.1:2.1.2`（ID `dab19726d88e`，2026-08-28 构建，revision `e6dacea0`）|
| Python | 3.10 |
| torch | 2.9.0+cu129 |
| flagtree | 0.6.1+xpu3.6（F 路径，`/opt/flagtree` 内 triton `3.6.0`）|
| vendor triton | 3.6.0+gitcd2d6c1b（T 路径，`/opt/triton`）|
| flag_gems | 5.3.5（双路径共享）|
| sglang | 0.5.18+flagos（cp310）|
| sgl-kernel-shim / flashinfer-shim | 0.5.18 / 0.1.0 |
| compressed-tensors | 0.17.0+flagos（`deps_app` pin）|
| sglang-plugin-FL | `exp/0.5.18-kunlunxin` @ `596820d`（`0.1.dev1+g596820d28`）|
| 模型 | Qwen3-4B（`/data/models/Qwen/Qwen3-4B`；节点无 0.6B）|

`(8, 6)` 是 kunlunxin 的 CUDA 兼容性标识，不是 NVIDIA SM 等级 —— 这个数字是本轮
多个阻塞的共同根因（§2.3）。

## 2. 修复链

五个阻塞：三个"从零安装起不来"，两个"起来后跑不动"。

| # | 阻塞 | 归属 |
|---|---|---|
| 1 | `compressed_tensors` 缺失：0.5.18 从 quantization 包无条件 import | build-infra `deps_app` pin（#857）|
| 2 | flashinfer 不存在但 `is_cuda()` 为真 → fp8_utils 模块级 import 崩 | build-infra `deps_app`（`flashinfer-shim`，#857）|
| 3 | 平台解析成 `nvidia` → `kunlunxin.yaml` 从未加载 | 插件 #104 |
| 4 | 0.5.18 API 漂移：`overlap_utils._resolve_future_token_ids` 已删 + KV pool 移出 `ForwardBatch` | 插件 #104 |
| 5 | JIT CUDA 谓词误报 True → nvcc 编 sm_86、启动报 `invalid device function` | 插件 #104 |

### 2.1 平台解析错位（#3）—— 本轮最大的一个

插件里 `get_platform_name()` 自行从 torch 属性推导厂商名，而不是问同一个插件里
其余部分都在用的 FlagGems 设备探测器。两条链在 CUDA-alias 栈上不一致：

```
get_device_info   -> kunlunxin
get_platform_name -> nvidia
config path       -> .../config/nvidia.yaml
flagos_blacklist  -> 0 entries
```

后果是 `kunlunxin.yaml` 里的**逐项二分出来的算子黑名单、`silu_and_mul` 的 vendor
路由、`oot_blacklist` 全部静默失效** —— 不是报错，是配置根本没被读。手写链只认识
torch 自己的设备命名空间，凡 CUDA-alias 厂商一律落到 `torch.cuda.is_available()`
分支。同一条链还让 `SGLANG_FL_PLATFORM` 在真机上不可达（提前 `return "nvidia"`
跑在 override 检查之前）。

修复 = 委托给 `sglang_fl.utils.get_device_info()`；env override 留在原地（它是
配置加载关注点，不是设备事实）。修复后黑名单 19 条正常加载。

### 2.2 0.5.18 API 漂移（#4）

- `overlap_utils._resolve_future_token_ids`（及其 `_native` 孪生）在 0.5.18 已删，
  遗留 rebind 在插件 import 期抛 AttributeError。**因为补丁是顺序执行的，这一个
  失败把所有在它后面的补丁一起废掉了** —— 整个 vendor 层从 0.5.18 起一直是死的。
- KV pool 从 `ForwardBatch` 移到 runner 上，十处 `forward_batch.token_to_kv_pool`
  需要改读 `model_runner.token_to_kv_pool`（在 `__init__` 里捕获一次，与 sglang
  自己的 attention backend 同法）。

补丁执行器同时改为逐个隔离，下一次 API 漂移不会再连带废掉其余补丁（本轮的
`causal_conv1d` 就受益于此，见 §5）。

### 2.3 JIT CUDA 谓词误报（#5）

sglang 里若干 `can_use_*` 谓词靠"把 kernel 编出来，编成功就返回 True"来判断：

```python
def can_use_x(...):
    try:
        _jit_x_module(...)   # nvcc，只编不跑
        return True
    except Exception:
        return False
```

编译目标跟着设备上报的 capability 走，而 kunlunxin 的 cuda-compat 设备答 `(8, 6)`，
于是 nvcc 合法地编出 sm_86 SASS：**编译成功，失败落在启动**，离做错决定的那个点很远：

```
RuntimeError: ... qknorm.cuh:173: CUDA error: invalid device function
RuntimeError: ... kvcache.cuh:316: CUDA error: invalid device function
```

`invalid device function` 是驱动在说"镜像里没有能跑在这块设备上的 SASS"。sm_86 是
NVIDIA 架构、本设备执行自己的指令集，所以**任何 nvcc 产出的 SASS 都不可能跑** ——
工具链是真 nvcc，恰恰是没人察觉的原因。修复 = 把这些谓词在**定义模块**和**已
from-import 的消费模块**两处都重绑为 `False`（名字在 import 时被复制，只改定义会
漏掉先 import 的调用方），让各自的 `except`/native 分支接手。

### 2.4 注意力改走 torch_native（#5 附带）

vendor backend 调 `sgl_kernel.klx_attention_extend` / `klx_attention_decode` ——
厂商编译的产物，不在我们发布的任何索引上，import 面 shim 也够不着（`torch.ops`
走 dispatcher，不读 Python 模块属性）。triton backend 也不是替代：XPU 编译器在
flash 风格 attention kernel 上失败（见
[vllm 侧记录](../../../../vllm/docs/handoffs/kunlunxin-xpu-triton-attention-compiler-bug.md)），
而 torch_native 同样会撞上 —— flag_gems 会劫持
`aten::_scaled_dot_product_flash_attention`。因此 `_ATTN_BACKEND_MAP` 把 kunlunxin
指向 `torch_native`，并把整个 SDPA 家族加进 `kunlunxin.yaml` 的 `flagos_blacklist`
（4 条），保留原生 torch 路径。

**这条改写了 [zero-sgl-kernel 可行性评估](../../zero-sgl-kernel-feasibility-20260828.md)
的 C 级结论**：klx_attention_* 不必移植进 flag_gems —— 零 sgl-kernel 路线在这里
靠 torch_native + SDPA 黑名单绕开了，代价是性能（未优化）。同文档的
`klx_fused_experts` / `klx_gated_delta_net` 两项未被本轮的 Qwen3 模型触达，仍在
C 级待办上。

## 3. E2E 验证（F/T 双路径）

判据：serve ready 后 3× chat/completions HTTP 200 + completion_tokens>0 +
`sampling_backend=pytorch`（经 `/server_info` 确认）。模型 Qwen3-4B，max_tokens 144。
**F 与 T 同一份配置，唯一变量是编译器**（两侧 `step7.out` 逐字节 diff，只差 ready
耗时；黑名单、env 开关、serve 参数全部同源）。

| 路径 | 编译器 | 结果 |
|---|---|---|
| F | flagtree 0.6.1+xpu3.6（triton 3.6.0）| ✅ ready ~170s，3/3，ct=144 |
| T | vendor triton 3.6.0+gitcd2d6c1b | ✅ ready ~100s，3/3，ct=144 |

两路径均在同一插件分支头 `0.1.dev1+g596820d28` 上验证，安装后依赖矩阵
（torch 2.9.0+cu129 / triton / flag_gems 5.3.5 / numpy 1.26.4）逐项不变；
`attention_backend=torch_native`、`sampling_backend=pytorch` 经 serve log 确认。

> 上一轮（2026-09-11）那台容器里的 3/3 是**手改 site-packages** 跑出来的：装进去的
> `platform.py` / `kunlunxin.yaml` 比 PR 头旧，serve 本身还因 `qknorm.cuh:173`
> 崩过一次。本轮的 ✅ 才是对 PR 头、干净容器的验证。

## 4. 交付配置

`deps_app.sglang0.5.18`（`configs.yaml`，PR #857 已并）：

| 包 | 用途 |
|---|---|
| `compressed-tensors==0.17.0+flagos` | quantization 链无条件 import |
| `flashinfer-shim==0.1.0` | `is_cuda()` 为真时 fp8_utils 的无条件 import |

`env.app.sglang`（同一 PR）：`TORCHINDUCTOR_COMPILE_THREADS=1`、
`SGLANG_IS_FLASHINFER_AVAILABLE=false`、`SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`。

`SGLANG_IS_FLASHINFER_AVAILABLE=false` 是**必需**而非省事：shim 让 `find_spec` 成功，
若不开这个开关，`is_flashinfer_available()` 后面的那些**带守卫的** flashinfer import
会真的去加载桩包、然后在更远处失败。

## 5. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | 黑名单必须写进 **platform config**，不能走 `SGLANG_FL_FLAGOS_BLACKLIST`：该 env 变量是**整体替换**平台列表而非追加，一设就把二分出来的 19 条全丢掉，serve 在完全另一个地方失败 | 写 `kunlunxin.yaml` |
| 2 | 补丁顺序执行 → 一个 AttributeError 静默废掉后面所有补丁（#4 的放大器，vendor 层因此死了整个 0.5.18）| 插件改为逐补丁隔离 |
| 3 | `can_use_*` 谓词"编译成功 = 可用"的判定在 CUDA-alias 设备上必然误报 —— 真 nvcc 编得出来，跑不了 | §2.3 重绑为 False |
| 4 | `causal_conv1d` 补丁在 0.5.18 上失败（`sglang.srt.layers.attention.mamba` 已无 `causal_conv1d_triton` 符号，实测 `dir()` 为空）| 隔离后降级为 warning；Qwen3 无 mamba，不影响本模型。**未修**，见 §6 |
| 5 | `fla_patch` 报 `No module named 'sglang.srt.layers.attention.fla'`（插件级，非 kunlunxin 特有）| 同上，降级日志；非本轮阻塞 |

## 6. 遗留

- 插件 PR #104 待合入 `exp/0.5.18`；正式 wheel 由 `sglang-plugin-wheel` workflow
  从该分支产出后才能进 app 镜像。
- `causal_conv1d` 补丁的目标路径在 0.5.18 已不存在（符号迁走），需要重指或删除；
  本轮靠隔离兜底、以 Qwen3（无 mamba）未触达为由未修。任何 mamba/GDN 模型
  （Qwen3-Next 等）在 kunlunxin 上会先撞这里。
- app 镜像未构建：`flagos-app/sglang0.5.18-{vendor}-{backend}` 的构建 + 镜像内
  serve E2E + tag 记录尚未做（本记录只覆盖 runtime + 单步安装路径）。
- 启动文档未生成（状态矩阵 `launch_docs: false`）。
- 性能未优化（torch_native 注意力）。
