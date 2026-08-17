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

结论：Metax 全线 4 种环境全部验证通过；NVIDIA 2 种 CUDA 环境（×双编译器）全部验证通过。

- 构建 + 重新打包（wheel）：✅ 通过（2026-08-12）
- MACA（3.7.2.1）× FlagTree：✅ 通过（2026-08-14）
- MACA（3.7.2.1）× Triton：✅ 通过（2026-08-13）
- MACA（3.8.1.3）× FlagTree：✅ 通过（2026-08-15）
- MACA（3.8.1.3）× Triton：✅ 通过（2026-08-15）
- CUDA 12.8 × FlagTree：✅ 通过（2026-08-16，空模式）
- CUDA 12.8 × Triton：✅ 通过（2026-08-16，空模式）
- CUDA 13.3 × FlagTree：✅ 通过（2026-08-16，空模式）
- CUDA 13.3 × Triton：✅ 通过（2026-08-16，空模式）

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
  torch 矩阵）。该 warmup 对非 MiniMaxM3 模型是 no-op，try/except 门控 +
  调用处判空即可。
- **这是换到 v0.3.0-dev 后仍需要的唯一补丁** —— 它属于 vLLM 0.24.0 wheel
  本身（site-packages），不属插件，不能进 vllm-plugin-FL PR。
  归属待定：进 repack 步骤（wheel 里直接打）还是 runtime 层（镜像装 torchvision）。

### 8.4 验证过程要点

- **stale `__pycache__` 陷阱**：插件源码打补丁后必须
  `find /opt/vllm-plugin-FL -type d -name __pycache__ -exec rm -rf {} +`，
  否则 serve 进程 import 的是旧字节码（曾把已修好的 DeepSeek-V4 门控
  问题再次以 `cublas_gemm` ImportError 形式暴露）。换 v0.3.0-dev 时同样
  先清 `__pycache__` 再 `pip install -e . --no-build-isolation`
  （head 构建依赖 `torch>=2.7.1`、`scikit-build-core==0.11`、`cmake`，
  必须 `--no-build-isolation`，否则 pip 隔离环境会从公共源拉 torch 覆盖矩阵）。
- **serve 启动逐级打通**（v0.3.0-dev）：EngineCore 初始化（`device_config=musa`、
  `backend=mccl`，DP/PP/PCP/TP rank 分配）→ 插件 OpManager
  （10 ops / 14 implementations，attention_backend `default.flagos` →
  `vendor.musa`）→ 权重加载（safetensors 2/2，约 5 秒）→ KV cache 初始化
  → kernel_warmup（在树门控仍生效）→ `Application startup complete`。
  插件换装是 editable install（`.pth` + finder），`vllm-plugin-fl==0.0.0`；
  插件无 `.so`（csrc 仅 ascend/cuda，`vllm_fl._C` import 为 try/except 门控）。
- **推理**：8031 端口两次请求均输出连贯 chain-of-thought（DeepSeek-R1
  模型正常思考）。✅ E2E 通过。

---

## 9. mthreads（MUSA 4.3.6）详细记录

- 节点：`mthreads`（JumpServer → 10.121.38.24），用户 `secure`
- 容器：`vllm-verify-mthreads-musa4.3.6`，MUSA SDK 4.3.6（torch 2.9.0+musa.4.3.6）
- venv：`/flagos`（cpython-3.10 —— 与 5.2.0 同为 cp310 wheel）
- 插件：v0.3.0-dev head（零补丁），editable install 于 `/opt/vllm-plugin-FL`
- 模型：`/data/DeepSeek-R1-0528-Qwen3-8B-FlagOS`
- 端口：8031

### 9.1 构建 + 安装

同 §8.1 —— 单步安装 `vllm==0.24.0+flagos`（cp310 wheel，命中 `+flagos`
wheel，无 torch 侧漏）；`pin_indirect: {xgrammar: "0.2.3"}` 同。

### 9.2 插件基线：v0.3.0-dev 零补丁

同 §8.2 —— v0.3.0-dev head（fbc115d），零补丁。serve 启动链与 5.2.0 一致：
OpManager **10 ops / 14 implementations** → attention_backend fallback
`default.flagos` → `vendor.musa` → 权重加载 → `Application startup complete`。
非致命遥测 fork 报错（`Cannot re-initialize MUSA in forked subprocess`）与
§8.2 相同，不影响服务。

### 9.3 编译器路径判定

**T 路径 ✅**（vendor triton 3.6.0+git89458660）：

- 触发算子：YaRN rotary-embedding `_compute_inv_freq` 中的
  `base ** pos_freqs`（base=1000000.0，1024 元素 MUSA float 张量）→
  flag_gems `pow_scalar` → `pow_func_scalar_tensor_kernel_rank_1_bptr_t1024`。
  该内核在 **vendor triton 下编译通过**（op 级 repro 输出
  `OK [1.0, 1.01358..., 1.02735...]`）。
- serve E2E ✅：`Application startup complete`；completions greedy 与
  chat CoT 均连贯；指纹 `vllm-0.24.0-5936039f`（5.2.0 为
  `vllm-0.24.0-423da8ca`）。
- 验证模型为 DeepSeek-R1-0528-Qwen3-8B-FlagOS（mthreads 节点无 Qwen3-4B），
  矩阵"Qwen3-4B"约定在此单元格不适用；原始 completions 直给 R1 模型 +
  temperature 0.6 的整段重复回声是模型行为伪影（同 §8.2）。

**F 路径 ✅（flagtree 0.6.1；configs 现 pin 0.6.0 需 bump）**：

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
2. **0.6.0→0.6.1 实验（2026-08-17）确认修复**：同一容器手动替换 flagtree
   为 **0.6.1+mthreads3.6**（whl `flagtree-0.6.1+mthreads3.6-cp310-cp310-...`，
   安装到 `/opt/flagtree061` 后整体替换 `/opt/flagtree`，原 0.6.0 保留在
   `/opt/flagtree060`）后：
   - op 级 repro 通过：同一 `base ** pos_freqs` 内核编译成功，输出
     `OK [1.0, 1.01358..., 1.02735...]`（0.6.0 下同脚本 SIGABRT）；
   - serve E2E ✅：`Application startup complete`（OpManager 10 ops / 14
     impls，rms_norm / silu_and_mul 走 `default.flagos`），completions greedy
     + chat CoT 均连贯；指纹 `vllm-0.24.0-5936039f`（同 T 路径，同容器同插件）。

结论：`self.base ** pos_freqs` 在 flagtree **0.6.1** 下可用 —— 0.6.0→0.6.1
即修复（不再对 `tl.exp2` 发出 vendor llc 不可选择的 `v2f32 = fexp2`）。
**configs.yaml 4.3.6 现 pin flagtree==0.6.0（F 路径坏），需 bump 到 0.6.1
并重建镜像后，单元格才对应交付物。** 5.2.0 自始即 0.6.1（§8，F 路径 ✅），
两者对齐后 mthreads 平台 F 路径全线一致。

---

## 10. 遗留事项

- [ ] `setuptools 84.0.0` 不满足 pyproject 中 `<81` 要求 —— 非致命问题，先不动，留意。
- [ ] 0.24.0 其余后端（hygon、iluvatar、enflame、sunrise、cambricon、
      ascend、kunlunxin 等）的验证 —— mthreads（§8 5.2.0 全通；§9 4.3.6
      T ✅ / F ✅*，`*` = flagtree 0.6.1 验证、configs 待 bump）；nvidia ✅（§6）
- [ ] mthreads-musa4.3.6 **configs.yaml flagtree 0.6.0→0.6.1 bump** + 镜像
      重建 —— 0.6.1 已验证修复 F 路径（§9.3），0.6.0 构建的镜像 F 路径
      仍不可用，重建后矩阵 `✅*` 才对应交付物

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
