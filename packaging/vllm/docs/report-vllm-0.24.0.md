# vllm 0.24.0 repack 端到端验证报告

> 我们把 vllm 0.24.0 重新打包成"不显式声明对 Torch/Triton 的依赖”的 Wheel 包。
> Wheel 包使用上游社区的 0.24.0 sdist 版本，使用 VLLM_TARGET_DEVICES=empty 模式编译。
> 这类 Wheel 包在安装的时候不会覆盖下层（Runtime）镜像中已经精心匹配、验证的版本矩阵。
> 新的 Wheel 包使用原来包的版本（`0.24.0`）加上 `+flagos` 以便区分，并且避免
> pip 等安装工具的时候错误选择其他 PyPI 源的同名、同版本软件包。
>
> 新的 Wheel 包在安装之后使用各 GPU/NPU 厂家所提供的运行时。
> 为确保最终生成的软件堆栈有效，需要逐个后端（Backend）地到对应的物理环境执行验证，
> 确保新的 Wheel 包及其依赖项能够正确安装、vLLM 软件栈可正常启动并执行推理任务。
> 本文记录 **metax（沐曦）** 与 **nvidia（英伟达）** 后端的验证过程与结果：
> - metax 见 §3–§5（MACA SDK 3.7.2.1 / 3.8.1.3 × 双编译器，4 环境全通过）；
> - nvidia 见 §6（CUDA 12.8 / 13.3 × 双编译器，空模式，全通过）。
>
> 类似的工作也在 0.20.2 版本的 vLLM 上开展，相关记录见
> [`report-vllm-0.20.2.md`](report-vllm-0.20.2.md)。

---

## 0. 结论摘要（TL;DR）

结论：Metax 全线 4 种环境全部验证通过；NVIDIA 2 种 CUDA 环境（×双编译器）全部验证通过；
Ascend（CANN 9.0.0）验证通过（插件 PR #387 移植，2026-08-17）。

- 构建 + 重新打包（wheel）：✅ 通过（2026-08-12）
- MACA（3.7.2.1）× FlagTree：✅ 通过（2026-08-14）
- MACA（3.7.2.1）× Triton：✅ 通过（2026-08-13）
- MACA（3.8.1.3）× FlagTree：✅ 通过（2026-08-15）
- MACA（3.8.1.3）× Triton：✅ 通过（2026-08-15）
- CUDA 12.8 × FlagTree：✅ 通过（2026-08-16，空模式）
- CUDA 12.8 × Triton：✅ 通过（2026-08-16，空模式）
- CUDA 13.3 × FlagTree：✅ 通过（2026-08-16，空模式）
- CUDA 13.3 × Triton：✅ 通过（2026-08-16，空模式）
- Ascend（CANN 9.0.0）× FlagTree：✅ 通过（2026-08-17，插件 PR #387，Qwen3-4B）

"通过" 意味着：1） vLLM 服务可以正常启动；2）使用 Qwen3-4B 模型可以执行正常推理服务；

**跨 SDK 版本兼容性事项**

- MACA SDK 3.7.2.1 中编译器版本为 Triton 3.0.0，MACA SDK 3.8.1.3 中 Triton 
  升级为 3.6.0 版本。Triton 3.0.0 不能很好地处理 vLLM 0.24.0 中使用的新版本
  Triton 语法，因此，在 MACA SDK 3.7.2.1 环境下选择 Triton 做编译器时，
  需要打补丁（链接？）。这些兼容性补丁的写法考虑了新版本 SDK 中 Triton
  已升级的情况，在新版本环境下也可正常运行。

- 所有用于适配的补丁都针对 vllm-plugin-FL 代码，不修改官方 vLLM 。

---

## 1. 背景

- vLLM 0.24.0 的构建脚本会尝试编译几个 Rust 组件。我们的构建容器没有 Rust 工具链，
  这些组件被静默跳过，产出一个"只有 Python 代码、没有任何编译产物"的 Wheel。

- Runtime 镜像里并列安装了 FlagTree 和 Triton 两个编译器，用 `compiler` 函数切换。
  与 MetaX 的两种 SDK 组合，形成 4 种环境（见 §3）。

---

## 2. 0.24.0 相比 0.20.2 的变化（只列影响打包的部分）

1. **引入两个 Rust 组件**：一个独立的前端进程（`vllm-rs`）和一个 Python 扩展
   （`vllm._rust_tool_parser`）。这两个组件默认关闭（使用 `VLLM_USE_RUST_FRONTEND=0`）。
   关闭时 vLLM 会忽略它们。只有服务 MiniMax M3 模型且开 tool calling 才会被 import。
   在不服务该模型的情况下，不会被触发。但**构建环境必须装 `setuptools-rust>=1.9.0`**
  （setup.py 无条件 import 它，缺了直接报错）；容器里没有 cargo（Rust 编译器）没关系，
   扩展声明为 optional，会被静默跳过，wheel 照常生成。

2. **empty wheel 绑定 Python 版本**：0.20.2 的 empty Wheel 是纯 Python（`py3-none-any`），
   可以跨 Python 版本复用。0.24.0 的 empty wheel 变成 `cp312-cp312-linux_x86_64`**。
   只要声明了 Rust 扩展，即使不编译任何 `.so` 文件，Wheel 也会被标记为与 CPython 版本相关。

   三个后果：Wheel 与 Python 小版本绑定，目前意味着需要 3.10、3.11、3.12 三个版本的后端。
   相同 Python 小版本的 Wheel 包是否可跨平台使用待测试给结论。
   另外 Wheel 中目前没有编译 Rust 库，意味着 `VLLM_USE_RUST_FRONTEND` 必须保持默认值 "0"。

3. **xgrammar 必须重新打包**：xgrammar 是 vLLM 的配套库。0.20.2 解析到 0.1.x，其中不带
   Torch/Triton 依赖的声明，因此不用处理。0.24.0 解析到 0.2.3，声明了对 `torch>=1.10.0`
   和 `triton` 的依赖。理论上，先安装了 Torch 和 Triton 之后，pip 安装时会检测到 Torch
   和 Triton 已经安装，不会覆盖。安全期间，也要做重新打包（repack）处理，形成
   `0.2.3+flagos` 版本（详见 §4.1）。

4. **构建脚本 / 配置规则微调**：之前用于 0.20.2 vLLM 的 `build-and-repack.sh` 脚本需要微调，
   构建依赖添加了 `setuptools-rust>=1.9.0` 和 `wheel` 两项；`config.yaml` 的依赖剥离规则随
   0.24.0 的依赖清单更新（新增剥离 `humming-kernels`、`quack-kernels`、`tokenspeed-mla`、
   `torch-c-dlpack-ext` 等 CUDA 内核库，清空不再依赖的 `apache-tvm-ffi`。

**待确认事项**

- **setuptools 版本问题**：Runtime 镜像中目前 `setuptools==84.0.0`，超出 vllm-plugin-FL
  的 pyproject.toml 所要求的 `<81`，可能会有问题。0.20.2 已验证 84 能构建，先保持不动。

---

## 3. 验证总览：metax 四环境矩阵

MetaX 两个后端的基础软件包和编译器版本不同，行为可能不同，要逐一验证。

- **3.7.2.1 + flagtree**：节点 metax123，torch 2.8.0，flagtree **0.6.1+metax3.6**
  （triton 3.6.0 基座，最新版）→ ✅ 2026-08-14（§4.3）
- **3.7.2.1 + triton**：节点 metax123，torch 2.8.0，triton 3.0.0+metax3.7.2.0
  → ✅ 2026-08-13（§4.2）
- **3.8.1.3 + flagtree**：节点 metax124，torch 2.10.0，flagtree 0.6.1+metax3.6
  → ✅ 2026-08-15（§5）
- **3.8.1.3 + triton**：节点 metax124，torch 2.10.0，triton 3.6.0+metax3.8.1.0
  → ✅ 2026-08-15（§5）

**被否决的配置：**

- MACA SDK 3.7.2.1 中内置了 FlagTree 3.1.0 版本的 Wheel 包，这一版本在 0.24.0 上有两个 API 缺口
  （`triton.jit` 缺 `do_not_specialize_on_alignment` 参数、缺 `knobs` 模块）。
  在验证 flagtree `0.6.1+metax3.6` 版本可用于此 SDK 版本之后，决定弃用厂商提供的
  flagtree 包，不再验证 3.1.0 版本 FlagTree。

---

## 4. SDK 3.7.2.1 详细记录

- 节点：`metax123`，MACA SDK 3.7.2.0
- 镜像：`flagos-runtime-metax-maca3.7.2.1:2.1.2-build`
- 模型： Qwen3-4B
- 参数：`--enforce-eager --dtype bfloat16`
- 端口： 8031/8032

### 4.1 构建 + repack

**两个构建问题（0.24.0 新增）：**

1. **缺少 `setuptools-rust` 直接 `ModuleNotFoundError`**：

   原因：setup.py 顶层无条件 import 此包。

   解决：构建依赖添加 `setuptools-rust>=1.9.0`。
   容器无 cargo 没问题（optional 扩展静默跳过）。

2. **构建源必须是 PyPI sdist，不能是 GitHub 源码包**：

   原因：GitHub 风格的 tarball 没有 `PKG-INFO`，`pip wheel` 报
   `LookupError: setuptools-scm was unable to detect version`。

   解决：换用含 `PKG-INFO` 的 sdist 后通过。

**构建产物（2026-08-12）：**

- empty wheel：`vllm-0.24.0+empty-cp312-cp312-linux_x86_64.whl`（7.6 MB）
- repack 输出：**`vllm-0.24.0+flagos-cp312-cp312-linux_x86_64.whl`**（7.5 MB）

**repack 结果：** 剥离了 3 个依赖的 Torch/Triton 声明，保留其余 47 项依赖：

- `compressed_tensors` `0.17.0+flagos`：剥离 `torch>=2.10.0`
- `opencv_python_headless` `5.0.0.93+flagos`：剥离两条 `numpy` 声明
- `xgrammar` `0.2.3+flagos`：剥离 `torch>=1.10.0` + `triton`

vLLM 顶层的依赖声明相应改成 `==X.Y.Z+flagos`，单步安装时命中厂家 PyPI 上的
`+flagos` Wheel，不会从公共源拉取未 repack 的版本。

### 4.2 安装 + 推理：遇到的问题

安装 vLLM + vllm-plugin-FL 后，启动推理服务过程中遇到的问题：

**前 5 个问题在新编译器（triton 3.6.0 基座）上都不存在**（§4.3 验证），
只有第 1 个是老 SDK（torch 2.8）特有的。

1. **vllm 0.24 无条件调用 `torch.accelerator` 的内存统计 API，
   metax 的 torch 只实现了其中一部分**
   这一问题导致 vLLM 启动即报 AttributeError。

   修复：在 Plugin 中把 `torch.cuda` 的对应函数（`memory_stats`、`memory_reserved`、
   `empty_cache`、`reset_peak_memory_stats` 等）绑回 `torch.accelerator`
   （Metax 上设备名就是 `"cuda"`）。其中 `reset_peak_memory_stats` 要包一层
   `try/except`：mtgpu 内存分配器初始化前显式传 device 会报错，
   无参调用兜底。

2. **一个算子的 import 路径在 0.24 里换了位置**
   （`gdn_linear_attn`，GatedDeltaNet 注意力）。

   修复：插件的 import 添加版本检测 ——
   0.24 前走旧路径、0.24 起走新路径。

3. **Triton 3.0.0 的一个类型处理 bug：`_load_ptr` 拒绝 constexpr 元素类型**。
   0.24.0 版本 vLLM 中恰好有一个内核把 `tl.int32` 传进去当元素类型，
   触发此缺陷。

   修复：`elem_dtype = elem_dtype.value` 无条件解包。
   **注意：不能用 `isinstance(elem_dtype, tl.constexpr)` 当判断依据**。
   Triton 在调用内建函数前会先解包 constexpr 实参，这个判断会一直为 False
   （0.24 上游源码也存在这一问题）。

4. **empty wheel 缺一个编译算子 `reshape_and_cache_flash`**。
   这个算子实现应该在 `_C_cache_ops` 中，empty 模式构建时需要替代实现。
   首次推理（KV-cache 预热）时会抛 AttributeError。

   修复：改用 `from flag_gems import reshape_and_cache_flash`
   （纯 Python 实现，签名逐参吻合）。
   **同一问题也存在于 0.20.2 版本适配中，已向插件提交 PR #333**。
   另外，vllm-plugin-FL 的 0.3-dev 分支也不存在此修复（详 §7）。

5. **Triton 3.0.0 编译器拒绝链式布尔操作**：`A or B or C` 语法报
   "chained boolean operators not supported"。

   修复：加括号 `(A or B) or C`，语义不变。
   0.24 版本中全量扫描，仅在采样路径中出现一次。

6. **Metax 的 UVA 内存视图是"CPU 类型"的张量**
   所谓 UVA 是指向设备可访问的固定内存，但 `device: cpu, is_cuda: False`。
   vLLM 假设这一视图是设备张量。
   Triton 内核能直接当指针读（`temperature`、`min_p`、`topk` 内核无需改），
   但 **Torch 用设备张量索引它就会出错**：

   - `get_top_k_top_p`（采样状态）：用设备索引 CPU 张量会引发
     `RuntimeError: indices should be either on cpu or on the same device`。
     修复方式是采用 CPU 索引。

   - 次生问题：结果变成 CPU 张量之后，MetaX 插件把 `apply_top_k_top_p` 路由到
     PyTorch 兜底实现，又在 CPU 建掩码 gather 到 CUDA 张量导致设备不一致。
     修复方式是在 CPU 索引后，执行 `.to(device)` 移回设备。

   - 池化路径 `prompt_len.gpu[idx_mapping]` 中存在同样问题，
     也需要使用 CPU 索引再移回设备。

   - 附带确认：`torch.device("metax")` 无效（设备字符串是 `"cuda"`）；
     `torch.frombuffer` 在 metax torch 上没有 `device=` 参数。

### 4.3 补丁清单与编译器决策

**补丁收敛在插件侧**。

- `vllm_fl/__init__.py`：`torch.accelerator` 内存 API shim（问题 1）
- `metax/patches/gdn_linear_attn.py`：version-gate 的 import（问题 2）
- `metax/impl/attention/utils/fa_utils.py`：`reshape_and_cache_flash`
  改用 flaggems 算子（问题 4）
- `metax/patches/vllm024_compat.py`（新建）：问题 3、5、6 的 4 个 monkey-patch，
  包括 `_load_ptr`（`.value` 解包 + 同步重赋值 `block_table._load_ptr`）、
  `_penalties_kernel`（链式布尔加括号）、`SamplingStates.get_top_k_top_p` +
  `PoolingRunner.pool`（UVA CPU 索引 + 移回设备）。
  方法 patch 用 `inspect.signature` 做版本门控（仅 0.24.0 签名生效），
  import 全部 try/except 兜底，旧版 vLLM 静默跳过
- `metax/patches/__init__.py`：注册 `vllm024_compat`

---

## 5. SDK 3.8.1.3详细记录

日期：2026-08-15
节点：`metax124`
镜像：`flagos-runtime-metax-maca3.8.1.3:2.1.2-build`
插件： main 分支 43edeb6（main）+ 本机未提交的 0.24.0 shim
端口：8033/8034

**验证过程注意事项：GPU 显存碰撞。**

vLLM 二次启动报 `ValueError: Free memory on device cuda:0 (2.02/63.59 GiB) on startup is less than desired GPU memory utilization (0.92, 58.51 GiB)`。
根因：上一次 serve 留下一个**孤儿 `VLLM::EngineCore` 进程**（约 10 GB 显存，
占了 GPU 0 长达 26 小时）。
由 bash 脱管 spawn，`pkill -f "port 8033"`、`pkill -f api_server` 都抓不到，
只能 `ps aux | grep EngineCore` 按 pid 杀。
**教训：杀 serve 后必须 `ps aux | grep -E "api_server|EngineCore"` 兜底检查孤儿进程。**

---

## 6. NVIDIA（CUDA 12.8 / 13.3）详细记录

日期：2026-08-16
节点：`h20`（H20 GPU，x86_64）
镜像：`flagos-runtime-nvidia-cuda12.8:2.1.2` / `flagos-runtime-nvidia-cuda13.3:2.1.2`
模型：Qwen3-4B（`/models/Qwen3-4B`，由 `/data/tqm/models` 挂载）
参数：`--enforce-eager --dtype bfloat16`，端口 8031/8032

### 6.0 插件基线：v0.3.0-dev

NVIDIA 路径使用 vllm-plugin-FL 的 **`v0.3.0-dev` 分支**（官方 0.24.0 适配线，
tar.gz 解包到 `/app/vllm-plugin-FL`；与 main 分支的差异与合并路线见 §7），
在 dev 分支上 **无需任何 monkey-patch**。

### 6.1 关键阻塞点与解决

1. **CUDA 平台无条件 import flashinfer**：0.24.0 的 CUDA 平台代码在
   `flashinfer_sampler_supported()` 中检查环境变量 `VLLM_USE_FLASHINFER_SAMPLER`
   （默认 True）后就 import flashinfer。Runtime 镜像未装 flashinfer，
   启动即报 import 错误。

   解决：启动时设置 **`VLLM_USE_FLASHINFER_SAMPLER=0`**（环境变量开关，
   非代码修改）。日志确认：`FlashInfer top-p/top-k sampling disabled via
   VLLM_USE_FLASHINFER_SAMPLER=0`。

2. **插件安装必须 `--no-build-isolation`**：pip 构建隔离会独立下载
   pyproject 声明的构建依赖 —— 其中 `torch>=2.7.1` 从 pypi.org 拉取约 2.4GB，
   且会**用下载的 torch 构建插件**。这与 repack 的初衷（保护 Runtime 镜像中
   精心匹配的版本矩阵）直接冲突，绝不允许。

   解决：先盘点 Runtime 环境已有工具链（setuptools 81.0.0、pybind11 3.0.3、
   ninja 1.13.0 已具备；缺 `wheel`、`scikit-build-core==0.11`、`cmake`），
   从**厂商 PyPI 索引**（`flagos-pypi-nvidia`）补齐缺失项，再
   `pip install -e . --no-build-isolation`（约 30 秒完成）。

   长期方案：随 §7 合并路线将插件以 **wheel 形式发布**后，源安装路径整体消失
   —— 预编译 wheel 不需要任何构建工具链，无需把 `wheel`/`scikit-build-core`/
   `cmake` 常驻进共享 Runtime 镜像（它们只为单步源安装临时补齐）。

### 6.2 验证结果

**CUDA 12.8（torch 2.10.0+cu128，python 3.12）**

- flagtree 3.6.0（`/opt/flagtree`，默认）：✅ 启动 + 推理通过
- triton 3.6.0（`/opt/triton`）：✅ 启动 + 推理通过
- 安装：`pip install vllm==0.24.0+flagos` 单步（`Using cached
  vllm-0.24.0%2Bflagos-cp312-cp312-linux_x86_64.whl (7.8 MB)`，无新下载）

**CUDA 13.3（torch 2.11.0+cu130，python 3.12）**

- flagtree 3.6.0：✅ 启动 + 推理通过
- triton 3.6.0：✅ 启动 + 推理通过
- 安装：插件 `--no-build-isolation` + vllm 单步

两种编译器、两个 CUDA 版本的推理输出完全一致：
`' Paris. The capital of Germany is Berlin. The capital of Italy is Rome.'`
（finish=length，模型指纹 `vllm-0.24.0-423da8ca`）。

### 6.3 跨 CUDA 版本复用（重要结论）

12.8 与 13.3 同为 python 3.12，**共用一个 cp312 empty wheel**
（`vllm-0.24.0+flagos-cp312-cp312-linux_x86_64.whl`）。13.3 验证同时回答了
"相同 cp 版本的 Wheel 是否可跨 CUDA 使用"：**12.8 构建的 wheel 直接在 13.3
（cu130）上单步安装并运行通过**。是否可跨 OS/架构（如 aarch64）仍待验证。

---

## 7. 版本推进协作问题

vllm-plugin-FL 项目组在 **`v0.3.0-dev`** 分支上展开 vLLM 0.24.0 适配工作。
在 #252 处与 main 分叉，尚未合入 main。适配主线：

- PR #274（升级 0.20.2→0.24.0）、
- PR #294（metax C550 适配）、
- PR #308（musa）、
- PR #334（mtp）、
- PR #338（CUDA stable-ABI wheels）

build-infra 验证用的基线是 main + PR #377，vllm-plugin-FL 的正式适配线是 v0.3.0-dev。
需要尽早确定合并路线。

两个分支的重叠/差异：

1. **`_patch_torch_accelerator()`（在 `__init__.py`）vs `accelerator_compat.py`
   —— 功能重复**：
   两边各写了一份 torch.accelerator 补丁。dev 版更严谨：先判断 torch 版本
   （<2.9 才动手）、再逐个查 API 在不在（缺才补）、补全了 6 个 API；
   main 上是早期写的老代码，只补了 `empty_cache` 一个。
   但 dev 版的 `reset_peak_memory_stats` 是直接赋值，**缺我们的 try/except 兜底**
   （torch 2.8 上 mtgpu 显式传 device 会报错）。
   **注意：torch 2.10+metax 上这些 API 原生齐全（实测）→ 两版补丁都不会触发，
   兜底只在 torch 2.8（老 SDK）生效。**

2. **`fa_utils.py` 改用 `flag_gems` 的 `reshape_and_cache_flash`，
   dev 仍用 `ops.reshape_and_cache_flash` —— dev 没处理 empty wheel 场景**：
   dev 分支 + empty wheel 组合未验证（问题 4 同因，
   0.20.2 #333 的修法没 upstream 过去）。

3. **`vllm024_compat.py`（问题 3/5/6 的 4 个补丁），dev 上不存在**：
   项目组没有使用过 3.1.0 的编译器，验证路径不同。
   我们的 4 个修复要不要 upstream 到 dev，待确认。

4. **dev 独有的 `chunk_delta_h.py` 的 USE_EXP2**（0.24.0 上游内核签名新增的参数）：
   我们没遇到的坑，验证路径未覆盖。

**待定事项：**
- [ ] **确认 0.24.0 正式发布线**：main（+ 我们补丁）还是 v0.3.0-dev？
      如果以 dev 为基线，§4 的验证要在 dev 分支上重验。
      **§6 的 NVIDIA 验证已在 dev 基线上完成（空模式、零 patch、双编译器全过）**，
      证明 dev 分支在 CUDA 上可直接交付；metax 侧则需要确认 3.0.0 编译器问题
      的 4 个补丁是否 upstream。
- [ ] `_patch_torch_accelerator` 与 `accelerator_compat.py` 去重：
      保留哪个版本；是否把 reset 的 try/except 兜底 backport 到 dev。
- [ ] 确认 dev 分支在 triton 3.0.0 路径是否缺问题 3/5/6 的修复（serve 冒烟即知）。
- [ ] dev 分支 + empty wheel：`reshape_and_cache_flash` 是否同样报错
      → flaggems 方案是否要 upstream 到 dev。
- [ ] 我们的验证路径补测 `USE_EXP2` 相关内核（chunk delta，Qwen3-Next/GDN 类模型）。

---

## 8. mthreads（MUSA 5.2.0）详细记录

- 节点：`mthreads`（JumpServer → 10.121.38.24），用户 `secure`
- 容器：`vllm-verify-mthreads-musa5.2.0`，MUSA SDK 5.2.0
- venv：`/flagos`（cpython-3.10 —— MUSA 路径走 cp310 wheel，区别于 NVIDIA 的 cp312）
- 模型：`/data/DeepSeek-R1-0528-Qwen3-8B-FlagOS`
- 端口：8031

### 8.1 构建 + 安装

- **pin_indirect 落地**：`packaging/vllm/config.yaml` 增加
  `pin_indirect: {xgrammar: "0.2.3"}`。0.24.0 对 xgrammar 的自身依赖自相矛盾
  （0.2.5 需要 torch/transformers 版本约束在 Runtime 矩阵上无法满足），
  xgrammar 锁到 0.2.3（`transformers>=4.38.0`，无上界，兼容 transformers 5.15.0），
  repack 后 METADATA 为 `xgrammar==0.2.3+flagos`。
- **单步安装**（厂商索引 + 阿里云镜像 extra）：
  `/flagos/bin/pip install --index-url
  https://resource.flagos.net/repository/flagos-pypi-mthreads/simple/
  --extra-index-url https://mirrors.aliyun.com/pypi/simple vllm==0.24.0+flagos`
  ✅ 通过，命中 `+flagos` wheel，无 torch 侧漏。

### 8.2 插件基线：v0.3.0-dev 零补丁（替代首轮的 main+8 处补丁）

**首轮验证**在 main 分支（db9afd6）+ 8 处本地补丁上完成（见下方历史清单）。
随后将容器插件换成 **v0.3.0-dev head（fbc115d）** 重跑 E2E：

- **结果：零补丁，全部通过。** 8 处 drift 修复在 v0.3.0-dev 上均有官方实现
  （已合入 PR #274 / #294 / #308 / #338 / #376），其中：
  - InputBatch 签名、`use_uniform_kv_cache` 单参 → model_runner.py:717 / :7300（#274）
  - FusedMoE 工厂函数注入 `_patch_fused_moe_factory`（custom_ops.py）
    → 替代我们的 `inspect.isclass` 门控 + OOT_OPS + oracle 方案
  - MarlinExperts / TritonExperts / rocm_aiter 新路径 → fused_moe_utils.py:19、router.py:9
  - flashinfer 惰性解析 → fused_moe_utils.py:171 内联
  - DeepSeek-V4：head 整体移除 deepseek_v4 模块族（与 0.24 上游同步），我们的门控 patch 无意义
- serve 启动链：OpManager **10 ops / 14 implementations**（head 重构后的 dispatch，
  规模小于 main 线的 35/65）→ attention_backend fallback `default.flagos` → `vendor.musa`
  → 权重加载 → `Application startup complete`
- 推理：chat/completions 输出连贯 CoT（DeepSeek-R1 正常思考）；completions greedy 输出连贯
- **非致命差异**：usage_lib 遥测线程报 `Cannot re-initialize MUSA in forked subprocess`
  （vllm 侧 `platform_utils` 用 fork 子进程查设备属性，MUSA 运行时 fork 后不可重初始化；
  仅遥测失败，不影响服务）。main+补丁基线无此报错，head 出现 —— 未追因，列入遗留。
- **原始 completions 直给 R1 模型 + temperature 0.6 出现整段重复回声**：是未套 chat
  模板的 R1 模型行为伪影，非插件缺陷（chat/completions 与 greedy 均正常）。

**历史记录：首轮 main 分支的 8 处 drift 修复（已被 v0.3.0-dev 官方实现取代，不再需要）**

MUSA 平台走插件路径（`PlatformFL` → device_type `musa`、dist_backend `mccl`），
0.24.0 的上游重构让插件暴露 8 处不兼容（main 线逐一修复）：

1. **`InputBatch.__init__` 签名变化**（`model_runner.py` 两处调用点）：
   0.24.0 删除 `pin_memory`、`is_spec_decode: bool` 改名 `num_spec_tokens: int`、
   新增 `reasoning_config`。插件已自算 `self.num_spec_tokens`，直接适配新签名。
2. **`use_uniform_kv_cache` 变 `@staticmethod`**：0.24.0 签名
   `use_uniform_kv_cache(attn_groups)`，`cache_dtype` 参数删除
   （统一布局决策移入 kv_cache_config）。调用点删掉 `cache_dtype` 实参。
3. **`FusedMoE` 从 PluggableLayer 子类变成工厂函数**（`fused_moe/layer.py`）：
   0.24.0 起 `def FusedMoE(...) -> MoERunner`，`class FusedMoEFL(FusedMoE)`
   无法定义。OOT MoE 层按 `inspect.isclass(FusedMoE)` 门控，
   非类时 `FusedMoEFL = None`，MoE 回退上游 oracle（
   `_patch_unquantized_moe_oracle` 无条件生效）。
4. **`MarlinExperts` 迁到 `fused_moe/experts/marlin_moe.py`**：
   `mxfp4_marlin.py` 的 import 改为新路径优先、旧路径 try/except 兜底。
5. **`TritonExperts` 迁到 `fused_moe/experts/triton_moe.py`**：同模式。
6. **`rocm_aiter_grouped_topk` 迁到 `fused_moe/router/grouped_topk_router.py`**：
   同模式。
7. **`get_flashinfer_moe_backend` 从 flashinfer_utils 删除**：改为惰性解析。
8. **DeepSeek-V4 OOT wrapper 门控**：`cublas_gemm_bf16_bf16_fp32`
   （`vllm.model_executor.layers.utils`）在 0.24.0 删除，0.24.0 上
   DeepSeek-V4 走上游，OOT wrapper 整体 try/except 门控。

### 8.3 上游 vllm 在树补丁（非插件，MUSA 验证的唯一残余补丁）

- **`kernel_warmup` 无条件 import `minimax_m3_msa_warmup`**：
  import 链到达 `torchvision.transforms`（`transformers_utils/processors/
  minimax_m3.py`），而 OOT Runtime 不装 torchvision（装它必然覆盖厂商匹配的
  torch 矩阵）。该 warmup 对非 MiniMaxM3 模型是 no-op。
- **归属已定：进插件调用侧（PR #386）** —— `kernel_warmup` 调用点在插件
  `vllm_fl/worker/worker.py`，在调用处 `try/except ImportError` 门控即可，
  不改 vllm wheel（wheel 保持与上游逐字节一致），也不在镜像里装 torchvision。
  这是 **0.24.0 全部无 torchvision OOT 后端（cambricon×2、hygon、ascend×2、
  mthreads×2）的通用前置修复**，见 §9.4。
- **早期 serve "零补丁" 的诚实注记**：5.2.0（§8.2）与 4.3.6 首轮（§9.2）
  的 serve 成功，实际依赖节点侧就地改写 site-packages 的
  `kernel_warmup.py`（`/tmp/patch_minimax_warmup.py`，不可复现），不是 wheel
  内建能力；重建镜像的新容器不补丁必崩（torchvision ImportError）。
  §8.2/§9.2 的"零补丁"仅指**插件**零补丁，vllm 在树补丁一直存在。
  可复现路径 = 插件 guard（PR #386），重建镜像后已按此路径重验（§9.4）。

### 8.4 验证过程要点

- **stale `__pycache__` 陷阱**：插件源码打补丁后必须
  `find /opt/vllm-plugin-FL -type d -name __pycache__ -exec rm -rf {} +`，
  否则 serve 进程 import 的是旧字节码（曾把已修好的 DeepSeek-V4 门控
  问题再次以 `cublas_gemm` ImportError 形式暴露）。换 v0.3.0-dev 时同样
  先清 `__pycache__` 再 `pip install -e . --no-build-isolation`
  （head 构建依赖 `torch>=2.7.1`、`scikit-build-core==0.11`、`cmake`，
  必须 `--no-build-isolation`，否则 pip 隔离环境会从公共源拉 torch 覆盖矩阵）。
- **serve 启动逐级打通**（v0.3.0-dev + torchvision guard）：EngineCore 初始化
  （`device_config=musa`、`backend=mccl`，DP/PP/PCP/TP rank 分配）→ 插件
  OpManager（10 ops / 14 implementations，attention_backend `default.flagos`
  → `vendor.musa`）→ 权重加载（safetensors 2/2，约 5 秒）→ KV cache 初始化
  → kernel_warmup（插件 guard 门控，见 §9.4）→ `Application startup complete`。
  插件换装是 editable install（`.pth` + finder），`vllm-plugin-fl==0.0.0`；
  插件无 `.so`（csrc 仅 ascend/cuda，`vllm_fl._C` import 为 try/except 门控）。
- **推理**：8031 端口两次请求均输出连贯 chain-of-thought（DeepSeek-R1
  模型正常思考）。✅ E2E 通过。

---

## 9. mthreads（MUSA 4.3.6）详细记录

- 节点：`mthreads`（JumpServer → 10.121.38.24），用户 `secure`
- 容器：`vllm-verify-mthreads-musa4.3.6`，MUSA SDK 4.3.6（torch 2.9.0+musa.4.3.6）
- venv：`/flagos`（cpython-3.10 —— 与 5.2.0 同为 cp310 wheel）
- 插件：v0.3.0-dev head + torchvision guard（PR #386），editable install 于 `/opt/vllm-plugin-FL`
- 模型：`/data/DeepSeek-R1-0528-Qwen3-8B-FlagOS`
- 端口：8031

### 9.1 构建 + 安装

同 §8.1 —— 单步安装 `vllm==0.24.0+flagos`（cp310 wheel，命中 `+flagos`
wheel，无 torch 侧漏）；`pin_indirect: {xgrammar: "0.2.3"}` 同。

### 9.2 插件基线：v0.3.0-dev + torchvision guard

插件 v0.3.0-dev head（fbc115d），除 **torchvision guard**（§8.3/§9.4，插件
PR #386 的调用侧补丁）外零补丁。serve 启动链与 5.2.0 一致：
OpManager **10 ops / 14 implementations** → attention_backend fallback
`default.flagos` → `vendor.musa` → 权重加载 → `Application startup complete`。
非致命遥测 fork 报错（`Cannot re-initialize MUSA in forked subprocess`）与
§8.2 相同，不影响服务。

**重建镜像复验（2026-08-17）**：configs bump（PR #414）后重建的镜像
（flagtree 0.6.1 烘焙于 `/opt/flagtree`），新容器首次 serve 因 torchvision
ImportError 崩溃（§9.4 首段）；应用插件 guard 后 F/T 双路径均重验 ✅
（F 见 §9.3，T 见 §9.4 末段）。早期首轮 serve 记录在 §9.3 的 0.6.0/0.6.1
实验中，仅作根因证据。

### 9.3 编译器路径判定

**T 路径 ✅**（vendor triton 3.6.0+git89458660）：

- 触发算子：YaRN rotary-embedding `_compute_inv_freq` 中的
  `base ** pos_freqs`（base=1000000.0，1024 元素 MUSA float 张量）→
  flag_gems `pow_scalar` → `pow_func_scalar_tensor_kernel_rank_1_bptr_t1024`。
  该内核在 **vendor triton 下编译通过**（op 级 repro 输出
  `OK [1.0, 1.01358..., 1.02735...]`）。
- serve E2E ✅（重建镜像复验 2026-08-17）：`Application startup complete`；
  completions greedy 与 chat CoT 均连贯；指纹 `vllm-0.24.0-5936039f`
  （5.2.0 为 `vllm-0.24.0-423da8ca`）。
- 验证模型为 DeepSeek-R1-0528-Qwen3-8B-FlagOS（mthreads 节点无 Qwen3-4B），
  矩阵"Qwen3-4B"约定在此单元格不适用；原始 completions 直给 R1 模型 +
  temperature 0.6 的整段重复回声是模型行为伪影（同 §8.2）。

**F 路径 ✅（flagtree 0.6.1 烘焙镜像，重建后复验）**：

1. **0.6.0 的失败（双层根因，镜像原状）**：
   a. **flag_gems 拦截 pow → flagtree codegen 失败**：`base ** pos_freqs` →
      `__rpow__` → flag_gems `pow_scalar` → `pow_func_scalar_tensor_kernel_rank_1_bptr_t1024`
      （pow.py:61:34，`tl.exp2`）→ flagtree 0.6.0+mthreads3.6 发出向量化
      `LLVM ERROR: Cannot select: v2f32 = fexp2` → vendor llc
      （`/usr/local/musa/bin/llc -march=mtgpu -mcpu=mp_31`）无法选择 → SIGABRT。
      报错前一行是 `llc` failed with error code -6。
   b. **黑名单排除 pow 后落入损坏的原生 torch 路径**：
      `VLLM_FL_FLAGOS_BLACKLIST=pow_scalar`（**正确排除名** —— flag_gems
      `config_filter` 按 Python 函数 `__name__` 匹配，不是 aten schema 名
      `pow.Scalar`；`enable(unused=["pow"])` 不生效）→ pow 不再被 flag_gems
      拦截（崩溃位置从 flag_gems pow.py 变为 `torch/_tensor.py:1113` 的
      `__rpow__`）→ 原生 `torch.pow(other, self)` →
      `RuntimeError: tensor.device().is_cpu() INTERNAL ASSERT FAILED at
      pybind_utils.cpp:590` —— torch 2.9.0+musa.4.3.6 无法处理 Python float
      底数 ** MUSA 张量指数。
2. **0.6.0→0.6.1 实验（2026-08-17）确认根因**：同一容器手动替换 flagtree
   为 **0.6.1+mthreads3.6**（whl `flagtree-0.6.1+mthreads3.6-cp310-cp310-...`，
   安装到 `/opt/flagtree061` 后整体替换 `/opt/flagtree`，原 0.6.0 保留在
   `/opt/flagtree060`）后：
   - op 级 repro 通过：同一 `base ** pos_freqs` 内核编译成功，输出
     `OK [1.0, 1.01358..., 1.02735...]`（0.6.0 下同脚本 SIGABRT）；
   - serve E2E ✅：`Application startup complete`（OpManager 10 ops / 14
     impls，rms_norm / silu_and_mul 走 `default.flagos`），completions greedy
     + chat CoT 均连贯；指纹 `vllm-0.24.0-5936039f`（同 T 路径，同容器同插件）。
3. **烘焙镜像复验（2026-08-17，configs bump #414 已合并）**：configs.yaml
   bump 后重建的镜像把 **0.6.1+mthreads3.6 烘焙于 `/opt/flagtree`**（不再
   手动替换）。F 路径（`compiler flagtree`）+ 插件 torchvision guard 下
   serve 到 `Application startup complete`、completions greedy + chat CoT
   均连贯、指纹 `vllm-0.24.0-5936039f`，与 T 路径完全一致。✅

结论：`self.base ** pos_freqs` 在 flagtree **0.6.1** 下可用 —— 0.6.0→0.6.1
即修复（不再对 `tl.exp2` 发出 vendor llc 不可选择的 `v2f32 = fexp2`）。
configs bump（PR #414）已合并、镜像已重建，4.3.6 F 路径对应交付物验证完成；
5.2.0 自始即 0.6.1（§8，F 路径 ✅），mthreads 平台 F 路径全线一致。

### 9.4 torchvision guard：0.24.0 通用 OOT 前置（插件 PR #386）

- **现象**：重建镜像的新容器（flagtree 0.6.1 烘焙）首次 serve 在 EngineCore
  init 崩溃 —— vllm 0.24.0 `kernel_warmup()` 无条件 import
  `minimax_m3_msa_warmup`，import 链到达 `torchvision.transforms`
  （§8.3），OOT runtime 不装 torchvision → `ImportError: No module named
  'torchvision'`。
- **为什么 5.2.0 / 4.3.6 早期 serve 没崩**：那些容器在节点侧就地改写
  site-packages 的 `kernel_warmup.py`（`/tmp/patch_minimax_warmup.py`）——
  不可复现，不属于任何 wheel。**重建镜像的新容器即复现**，排除了
  "wheel 自带补丁" 的误判。
- **修复（插件调用侧，PR #386）**：`kernel_warmup(self)` 调用处
  `try/except ImportError` 门控 + warning（warmup 对非 MiniMaxM3 是 no-op）。
  不改 vllm wheel（与上游逐字节一致），不装 torchvision（不污染厂商 torch
  矩阵）。**影响全部无 torchvision OOT 后端**：cambricon×2、hygon、
  ascend×2、mthreads×2。
- **复验**：同一新容器应用 guard 后（`/opt/vllm-plugin-FL/vllm_fl/worker/
  worker.py`，与 PR #386 逐字相同，compile OK）→ F/T 双路径 serve 均到
  `Application startup complete`、推理连贯、指纹 `vllm-0.24.0-5936039f`。

---

## 10. ascend（CANN 9.0.0）详细记录

- 镜像：`flagos-runtime-ascend-cann9.0.0:2.1.2`（aarch64，CANN 9.0.0，
  驱动 26.0.rc1，设备 Ascend910B4）
- venv：`/flagos`（cpython-3.11 —— aarch64 走 cp311 empty wheel）
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
  自有实现覆盖部分算子，其余回退默认实现（同 mthreads 模式）。
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
  列入遗留（§11）。
- **GDN/hybrid 模型（Qwen3-Next）0.24.0 暂不支持**：0.24.0 把
  `mamba/gdn_linear_attn.py` 重构为 `mamba/gdn/` 包，patch.py 的 GDN
  补丁目标符号失效（try/except 静默 no-op）。plain-attention 模型
  （Qwen3、Qwen2、Llama…）不受影响；重构 GDN 补丁为后续工作。

### 10.3 cann8.5.0（hw26）双编译器验证

- 镜像：`flagos-runtime-ascend-cann8.5.0:2.1.2`（aarch64，CANN 8.5.0，
  Ascend910B4，节点 hw26）
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

### 10.4 cann9.0.0 triton 路径 E2E（hw25，2026-08-18）

补上 §10.2 缺失的 triton 侧验证（cann9.0.0 此前未单独 serve triton
路径；cann8.5.0 的 triton 侧见 §10.3）：

- 镜像/容器：`flagos-runtime-ascend-cann9.0.0:2.1.2` 重建（PR #428
  triton overlay unzip 修复后），容器 `vllm-triton-cann9`，节点 hw25
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

### 10.5 app 镜像 serve E2E（hw25，2026-08-18）

§10.1–10.4 均为 runtime 镜像 + editable 插件；本节验证**交付形态**：
app 镜像（wheel 单步安装线 + `vllm-serve` launcher）在 NPU 上的
serve + 推理，即 `app/vllm/` 全流程的端到端证明。

- 镜像：`harbor.baai.ac.cn/flagos-dev/vllm-ascend-cann9.0.0:2.1.2`
  （构建 run 32146899749，已 push）
- 版本指纹：vllm `0.24.0+flagos`（cp311 aarch64 empty wheel，
  单步安装）；vllm-plugin-fl `0.2.0+gcf8998c.d20260818`（vendor PyPI
  wheel，非 editable —— setuptools-scm 编码同 §10.4 的 `cf8998c`
  commit，同一 PR #387 代码）；torch 2.10.0+cpu / torch_npu 2.10.0 /
  flag_gems 5.3.4；torchvision/torchaudio 未安装（OOT 矩阵保持）；
  编译器 = 默认 flagtree 0.6.1+ascend3.5（`VLLM_PLUGINS=fl` 烘焙）
- 启动：`vllm-serve`（`/etc/bash_env.sh` 源入 vendor env →
  `exec api_server`），`docker run` 裸 `--device` flags，容器
  `vllm-app-smoke`，端口 8031：
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
  `vllm-triton-cann9` 持有 `/dev/davinci0`**（其 python 进程已
  defunct，但 NPU 句柄未释放，容器外 open 报 `EBUSY`；容器内
  torch_npu 探测到 0 设备）。`docker rm -f` 该遗留容器后，同一 launch
  立即 `device_count=1`，serve 全绿。教训：ascend 节点上
  "容器已 Exited/僵尸但设备仍被占用" 会让后续容器静默看到 0 设备 ——
  serve 前先 `npu-smi info -t proc-mem` 确认设备空闲（本次宿主侧
  proc-mem 显示 "No process in device" 与真实占用不一致，须以
  `docker ps -a` + 设备 open 实测为准）。

---

## 11. 遗留事项

- [ ] `setuptools 84.0.0` 不满足 pyproject 中 `<81` 要求 —— 非致命问题，先不动，留意。
- [x] **插件 PR #386（torchvision guard）合入 v0.3.0-dev** —— 2026-08-17
      已合入（5b592be）；ascend 验证即基于该基线（§10）。
- [ ] 0.24.0 其余后端（hygon、iluvatar、enflame、sunrise、cambricon、
      kunlunxin 等）的验证 —— mthreads（§8 5.2.0 全通；§9 4.3.6
      T ✅ / F ✅，烘焙镜像双路径复验 2026-08-17）；nvidia ✅（§6）；
      ascend ✅（§10，CANN 9.0.0 + cann8.5.0 双编译器）
- [ ] ascend flag_gems 5.3.4 `index_select.py:45` 逻辑 and/or 弃用警告
      （§10.2，非致命）—— 上游 flag_gems 侧修复后复验

---

## 附录 · 验证命令（容器内）

metax 形式（含 `compiler` 切换 + `VLLM_USE_FLASHINFER_SAMPLER=0`，NVIDIA 通用）：

```bash
cd /app/vllm-plugin-FL && compiler flagtree && VLLM_USE_FLASHINFER_SAMPLER=0 \
  nohup /flagos/bin/python -m vllm.entrypoints.openai.api_server \
  --model /models/Qwen3-4B --port 8031 --enforce-eager --dtype bfloat16 \
  > /tmp/serve.log 2>&1 &

curl -s localhost:8031/v1/completions -H 'Content-Type: application/json' \
  -d '{"model":"/models/Qwen3-4B","prompt":"The capital of France is","max_tokens":16,"temperature":0}'
```

NVIDIA 插件安装 —— 仅当前源安装路径需要（必须 `--no-build-isolation`，缺失工具链
从厂商 PyPI 补齐）；插件以 wheel 形式发布后（§7 合并路线），此块整体省略：

```bash
/flagos/bin/pip install --no-cache-dir wheel scikit-build-core==0.11 cmake \
  -i https://resource.flagos.net/repository/flagos-pypi-nvidia/simple/ \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple
cd /app/vllm-plugin-FL && /flagos/bin/pip install -e . --no-build-isolation
/flagos/bin/pip install vllm==0.24.0+flagos
```
