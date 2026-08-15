# vllm 0.24.0 repack 端到端验证报告

> **这份报告在说什么？** 我们把 vllm 0.24.0 重新打包成"不带官方 torch/triton、改用各 GPU/NPU 厂家自家运行时"的 wheel（叫 **+flagos wheel**），再到真机上逐后端验证：装得上、启动得起、能推理。本文记录 **metax（沐曦）** 后端的验证过程与结果。
>
> 0.20.2 的同类记录见 [`report-vllm-0.20.2.md`](report-vllm-0.20.2.md)。看不懂的名词先看 §1 术语表。

---

## 0. 结论摘要（TL;DR）

**一句话：metax 全线 4 种环境全部验证通过 —— vllm 0.24.0+flagos wheel 在真机上装得上、服务起得来、推理结果正确，且不需要改 vllm 官方代码。**

| 验证项 | 结果 |
|---|---|
| 构建 + 重新打包（wheel） | ✅ 通过（2026-08-12） |
| 老 SDK（3.7.2.1）× 编译器 flagtree | ✅ 通过（2026-08-14） |
| 老 SDK（3.7.2.1）× 编译器 triton | ✅ 通过（2026-08-13） |
| 新 SDK（3.8.1.3）× 编译器 flagtree | ✅ 通过（2026-08-15） |
| 新 SDK（3.8.1.3）× 编译器 triton | ✅ 通过（2026-08-15） |

"通过"= 启动 vllm 服务不崩 + 用 Qwen3-4B 问一句「The capital of France is」，4 种环境返回完全一致的正确输出。

**两个值得记住的结论：**

1. **两种编译器行为一致，补丁不用分别维护。** 为老编译器（triton 3.0.0）写的 6 个兼容补丁，在新编译器（triton 3.6.0 基座）上全部自动失效且无害 —— 不需要按编译器维护两套。
2. **所有适配都在插件里，vllm 官方 wheel 保持原样。** 和 0.20.2 的做法一致（架构上干净：升级 vllm 时不用回改）。

---

## 1. 背景：先解释几个词（术语表）

不熟悉这套东西的读者请先看这一段，正文里会直接使用这些词。

- **repack（重新打包）**：vllm 官方 wheel 声明依赖官方 torch / triton。各 GPU/NPU 厂家用的是**自家改过的 torch**（如 metax 的 `torch 2.10+metax`），装了官方 torch 会冲突。所以我们要把 vllm 的依赖列表里 torch、triton 等"换血"成厂家版本，重新打成 wheel —— 这个动作叫 **repack**，产物叫 **+flagos wheel**。
- **empty wheel（空 wheel）**：vllm 0.24.0 的构建脚本会尝试编译几个 Rust 组件。我们的构建容器没有 Rust 工具链，这些组件被静默跳过，产出一个"只有 Python 代码、没有任何编译产物"的 wheel —— 叫 **empty wheel**。它仍然能工作（vllm 会自动走 Python 路径），但要靠 repack 补全依赖才能用。
- **flagtree / triton（两种编译器）**：都是把 GPU 内核代码编译成机器码的工具。**flagtree 是 FlagOS 生态的默认编译器**（基于 triton 改的），triton 是官方版。运行时镜像里两种都装了，用 `compiler` 函数 / `PYTHONPATH` 切换。metax 的两种 SDK 各配两套编译器，所以有 4 种环境（见 §3）。
- **插件（vllm-plugin-FL）**：vllm 的扩展机制。所有厂家适配都放在这个插件里，**不碰 vllm 本体代码**。
- **shim（垫片）**：为了兼容新旧版本而写的一小段适配代码，挂在插件里。
- **version-gate（版本闸门）**：代码里加个判断"只在特定版本范围内才执行"，避免误伤不适用的情况。
- **no-op（空操作）**：补丁的生效条件不满足时，什么都不做、毫无副作用。
- **冒烟（smoke test）**：最基本的验证 —— 服务能起、能答对一句最简单的提问。

**正文中会用到、到时再解释：** UVA（metax 卡的内存统一寻址）、constexpr（编译期常量）。

---

## 2. 0.24.0 相比 0.20.2 的变化（只列影响打包的部分）

| 变化 | 人话解释 | 影响 |
|---|---|---|
| **引入两个 Rust 组件** | 0.24.0 用 Rust 写了两个东西：(1) 一个独立的前端进程 `vllm-rs`，(2) 一个 Python 扩展 `vllm._rust_tool_parser`。 | **可忽略，不是碰运气**：(1) 默认关闭（环境变量 `VLLM_USE_RUST_FRONTEND` 默认 `"0"`），关闭时 vllm 根本不去找它；(2) 只有服务 MiniMax M3 模型且开 tool calling 才会被 import，我们不服务该模型 → 永远不触发。但**构建环境必须装 `setuptools-rust>=1.9.0`**（setup.py 无条件 import 它，缺了直接报错）；容器里没有 cargo（Rust 编译器）没关系，扩展声明为 optional，会被静默跳过，wheel 照常生成。 |
| **empty wheel 绑定 Python 版本（重要）** | 0.20.2 的 empty wheel 是纯 Python（`py3-none-any`），可以跨 Python 版本复用（hygon 曾直接拿 mthreads 的 wheel 用）。**0.24.0 的 empty wheel 变成 `cp312-cp312-linux_x86_64`** —— 只要声明了 Rust 扩展，即使一个 .so 都没编译出来，wheel 也会被标记为平台相关。 | 三个后果：(a) 按 Python 小版本绑定，跑 3.10/3.11 的后端（ascend、hygon、kunlunxin、mthreads、sunrise、tsm、cambricon-4.4.3）装不了 cp312 产物，须在各自镜像内自己构建（构建脚本本来就是 per-backend 的，自洽）；(b) "跨后端复用 +flagos wheel"不再成立，只有同 Python 版本间可复用；(c) wheel 里没有 Rust 二进制 → `VLLM_USE_RUST_FRONTEND` 必须保持默认 False，走 Python 路径。 |
| **xgrammar 必须 repack（重要）** | xgrammar 是 vllm 的配套库。0.20.2 解析到 0.1.x，不带 torch/triton 依赖 → 不用处理。**0.24.0 解析到 0.2.3，声明了 `torch>=1.10.0` + `triton`** → 必须一起 repack，否则单步安装会把官方 torch 拉回来。0.20.2 报告里"xgrammar 不需处理"的说法作废。 | repack 后变成 `xgrammar==0.2.3+flagos`（详见 §4.1）。 |
| **构建脚本 / 配置规则小改** | `build-and-repack.sh` 的构建依赖加了 `setuptools-rust>=1.9.0` 和 `wheel`；`config.yaml` 的依赖剥离规则随 0.24.0 的依赖清单更新（新增剥离 `humming-kernels`/`quack-kernels`/`tokenspeed-mla`/`torch-c-dlpack-ext` 等 CUDA 内核库，清空不再依赖的 `apache-tvm-ffi`）。 | 构建侧例行更新，无验证风险。 |

**待确认（不阻塞）：** `setuptools 84.0.0` 超出 pyproject 要求的 `<81` 是否造成问题 —— 0.20.2 已验证 84 能构建，先保持不动。

---

## 3. 验证总览：metax 四环境矩阵

metax 有两种 SDK 后端（老 3.7.2.1 / 新 3.8.1.3），每种 SDK 配两套编译器（flagtree 默认 / triton 侧装），共 **2 后端 × 2 编译器 = 4 种环境**。老 SDK 的 triton 是 3.0.0，新 SDK 的 triton 是 3.6.0 —— 编译器版本不同，行为可能不同，所以要逐一验证（此前 kunlunxin 的 flagtree 编译失败、sunrise 的 flagtree 解码卡死都是先例）。

| 环境 | 节点 | torch | 编译器 | 状态 |
|---|---|---|---|---|
| 3.7.2.1 + flagtree | metax123 | 2.8.0 | flagtree **0.6.1+metax3.6**（triton 3.6.0 基座，最新版） | ✅ 2026-08-14（§4.3） |
| 3.7.2.1 + triton | metax123 | 2.8.0 | triton 3.0.0+metax3.7.2.0 | ✅ 2026-08-13（§4.2） |
| 3.8.1.3 + flagtree | metax124 | 2.10.0 | flagtree 0.6.1+metax3.6 | ✅ 2026-08-15（§5） |
| 3.8.1.3 + triton | metax124 | 2.10.0 | triton 3.6.0+metax3.8.1.0 | ✅ 2026-08-15（§5） |

> 另有一行被否决的组合：**3.7.2.1 + flagtree 3.1.0**（SDK 对齐版）在 0.24.0 上有两个 API 缺口，见 §4.3 —— 已决定弃用，不列入验证。

---

## 4. 老 SDK（3.7.2.1）详细记录

节点 `metax123`，容器 `vllm-dbg-metax`，镜像 `flagos-runtime-metax-maca3.7.2.1:2.1.2-build`，模型 Qwen3-4B（`--enforce-eager --dtype bfloat16`，端口 8031/8032）。

### 4.1 构建 + repack

**两个构建坑（0.24.0 新增）：**
1. **缺 `setuptools-rust` 直接 `ModuleNotFoundError`**（setup.py 顶层无条件 import）→ 构建依赖已补 `setuptools-rust>=1.9.0`。容器无 cargo 不致命（optional 扩展静默跳过）。
2. **构建源必须是 PyPI sdist，不能是 GitHub 源码包**：GitHub 风格的 tarball 没有 `PKG-INFO`，`pip wheel` 报 `LookupError: setuptools-scm was unable to detect version`。换用含 `PKG-INFO` 的 sdist 后通过。**后续后端若再遇此错，先核对 tarball 是否含 `PKG-INFO`。**

**构建产物（2026-08-12）：**
- empty wheel：`vllm-0.24.0+empty-cp312-cp312-linux_x86_64.whl`（7.6 MB）
- repack 输出：**`vllm-0.24.0+flagos-cp312-cp312-linux_x86_64.whl`**（7.5 MB，`+empty` → `+flagos`）

**repack 修了两个自身 bug**（首次运行产出 `repacked_deps: []`，应为 3 项）：
1. 主路径 `pip install --dry-run --report` 失败后被 `except: pass` 静默吞掉，直接返回空结果 → 改为记录失败原因再回退。
2. 回退逻辑请求的 Aliyun **PEP-503 JSON API 不存在**（实测所有包都 404）→ 改用 `pip index versions`（走 Aliyun 的 HTML simple 索引，可用）。

**repack 结果：** 剥离了 3 个依赖的 torch/triton 声明，保留 47 项：

| repacked dep | 版本 | 剥离了什么 |
|---|---|---|
| `compressed_tensors` | `0.17.0+flagos` | `torch>=2.10.0` |
| `opencv_python_headless` | `5.0.0.93+flagos` | 两条 `numpy` 声明 |
| `xgrammar` | `0.2.3+flagos` | `torch>=1.10.0` + `triton` |

vllm 顶层的依赖声明相应改成 `==X.Y.Z+flagos`，单步安装时命中厂家索引上的 +flagos wheel，不会从公共源拉回未 repack 的版本（也就不再漏回官方 torch/triton）。

### 4.2 安装 + 推理：遇到的 6 个问题

安装 vllm wheel + 插件后，第一轮 serve 连续崩溃。以下按崩溃顺序列出 6 个问题、各一句话人话 + 细节。**前 5 个问题在新编译器（triton 3.6.0 基座）上都不存在**（§4.3 验证），只有第 1 个是老 SDK（torch 2.8）特有的。

1. **vllm 0.24 无条件调用 `torch.accelerator` 的内存统计 API，metax 的 torch 只实现了其中一部分** → 启动即 AttributeError。
   修：插件把 `torch.cuda` 的对应函数（`memory_stats`/`memory_reserved`/`empty_cache`/`reset_peak_memory_stats` 等）绑回 `torch.accelerator`（metax 上设备名就是 `"cuda"`）。其中 `reset_peak_memory_stats` 要包一层 try/except：mtgpu 内存分配器初始化前显式传 device 会报错，无参调用兜底。

2. **一个算子的 import 路径在 0.24 里换了位置**（`gdn_linear_attn`，GatedDeltaNet 注意力）。
   修：插件的 import 改成 version-gate —— 0.24 前走旧路径、0.24 起走新路径，同一份代码两边兼容。

3. **triton 3.0.0 的一个类型处理 bug：`_load_ptr` 收到 constexpr 元素类型就拒绝**（`element_ty is a constexpr.`）。0.24 恰好有一个内核把 `tl.int32` 传进去当元素类型，触发。
   修：`elem_dtype = elem_dtype.value` 无条件解包。**注意：不能用 `isinstance(elem_dtype, tl.constexpr)` 当守卫** —— triton 在调用内建函数前会先解包 constexpr 实参，这个判断恒为 False（0.24 上游源码正是这么写的，照抄必挂）。

4. **empty wheel 缺一个编译算子 `reshape_and_cache_flash`**（在 `_C_cache_ops` 里，empty 构建没有）→ 首次推理（KV-cache 预热）AttributeError。
   修：改用 `from flag_gems import reshape_and_cache_flash`（纯 Python 实现，签名逐参吻合）。**这是 0.20.2 #333 的同款问题**，但 0.24 的插件没带上这个修复，得在插件侧再打一遍（详 §6：dev 分支同样没带）。

5. **triton 3.0.0 编译器拒绝链式布尔**：`A or B or C` 三连链报"chained boolean operators not supported"。
   修：加括号 `(A or B) or C`，语义不变。0.24 采样路径里唯一一处，已全量确认。

6. **metax 的 UVA 内存视图是"CPU 类型"的张量**（指向设备可访问的固定内存，但 `device: cpu, is_cuda: False`），而 vllm 假设它是设备张量。triton 内核能直接当指针读（temperature/min_p/topk 内核无需改），但 **torch 用设备张量索引它就会炸**：
   - `get_top_k_top_p`（采样状态）：用设备索引 CPU 张量 → `RuntimeError: indices should be either on cpu or on the same device`。修：CPU 索引。
   - 次生问题：结果变成 CPU 张量，metax 插件把 `apply_top_k_top_p` 路由到 PyTorch 兜底实现，又在 CPU 建掩码 gather 到 cuda 张量 → 设备不一致。修：CPU 索引后 `.to(device)` 移回设备。
   - 同类：池化路径 `prompt_len.gpu[idx_mapping]` → 同样 CPU 索引 + 移回设备。
   - 附带确认：`torch.device("metax")` 无效（设备字符串是 `"cuda"`）；`torch.frombuffer` 在 metax torch 上没有 `device=` 参数。

### 4.3 补丁清单与编译器决策

**补丁收敛在插件侧（vllm wheel 保持原样）** —— 和 0.20.2 架构一致。第一轮验证先直接改了 site-packages，随后收敛为插件 monkey-patch，并把 4 处 site-packages 恢复原样（md5 校验）后重验通过：

| 插件文件 | 改了啥 |
|---|---|
| `vllm_fl/__init__.py` | `torch.accelerator` 内存 API shim（问题 1） |
| `metax/patches/gdn_linear_attn.py` | version-gate 的 import（问题 2） |
| `metax/impl/attention/utils/fa_utils.py` | `reshape_and_cache_flash` 改用 flag_gems（问题 4） |
| `metax/patches/vllm024_compat.py`（新建） | 问题 3/5/6 的 4 个 monkey-patch：`_load_ptr`（.value 解包 + 同步重赋值 `block_table._load_ptr`）、`_penalties_kernel`（链式布尔加括号）、`SamplingStates.get_top_k_top_p` + `PoolingRunner.pool`（UVA CPU 索引 + 移回设备）。方法 patch 用 `inspect.signature` 做版本门控（仅 0.24.0 签名生效），import 全部 try/except 兜底，旧版 vLLM 静默跳过 |
| `metax/patches/__init__.py` | 注册 `vllm024_compat` |

**编译器决策（2026-08-14，重要）：flagtree 全线用最新版 0.6.1+metax3.6，弃用 3.1.0。**
背景：默认编译器路径原先是 flagtree 3.1.0（对齐 3.7.2.1 SDK 的版本），在 vllm 0.24.0 上有两个 API 缺口（`triton.jit` 缺 `do_not_specialize_on_alignment` 参数、缺 `knobs` 模块），插件打了两个 version-gate 的补丁（patch #5/#6）兜住。但判断 **flagtree 团队不按 MACA SDK 版本对齐**，于是直接试为 3.8.1.x 构建的最新版 **0.6.1+metax3.6**（triton 3.6.0 基座，对齐 torch 2.10）看老 SDK 能否直接跑 —— **结果能，零新增补丁**：
- 0.6.1 在老 SDK（3.7.2.1 / torch 2.8）上直接可用，serve + 推理通过，输出与 triton 3.0.0 完全一致。
- triton 3.6.0 基座自带那两个 API（`knobs` 存在、`do_not_specialize_on_alignment` 存在）→ patch #5/#6 自动 no-op。
- 顺带印证：triton 3.0.0 特有的 4 个问题（§4.2 的 3/5/6）在 3.6.0 上不存在，相关 shim 应用后无害。

决策落地：metax123 容器 `/opt/flagtree` 换成 0.6.1；configs.yaml 的 maca3.7.2.1 flagtree pin 改为 `0.6.1+metax3.6`；为 3.1.0 写的 patch #5/#6 保留但不再需要。

---

## 5. 新 SDK（3.8.1.3）详细记录

节点 `metax124`，容器 `vllm-dbg-metax3813`，镜像 `flagos-runtime-metax-maca3.8.1.3:2.1.2-build`（`/vllm-repack` 中已装 vllm 0.24.0+flagos）。

**环境盘点：**
- torch **2.10.0+metax3.8.1.0**，vllm 0.24.0+flagos
- `/opt/flagtree` = **0.6.1+metax3.6**（triton 3.6.0 基座）、`/opt/triton` = **3.6.0+metax3.8.1.0**（侧装），`compiler` 函数两套都可用
- ⚠️ pip 命名空间里还残留一个 triton **3.7.1**（源码安装残留）。serve 靠 `PYTHONPATH=/opt/triton` 显式覆盖，**实际生效的是 3.6.0**；但如果有人不设 PYTHONPATH 直接 `import triton` 会踩到 3.7.1。可考虑容器里 `pip uninstall triton` 收敛，待定。
- 插件 @ 43edeb6（main）+ 本机未提交的 0.24.0 shim

**两套编译器冒烟结果（2026-08-15）：**
- **flagtree（默认路径）**：端口 8033，startup 干净，输出与其它 3 个环境完全一致。
- **triton（侧装路径）**：端口 8034（前序会话已启动，直接复用），输出一致。
- **零新增补丁** —— §4.3 的结论在 3.8.1.3 上成立：triton 3.0.0 特有的问题不存在，shim 全部安全 no-op。**不需要按编译器或 SDK 分别维护补丁。**

**验证过程中踩的一个坑（已解决，值得记住）：GPU 显存碰撞。** flagtree serve 二次启动报 `ValueError: Free memory on device cuda:0 (2.02/63.59 GiB) on startup is less than desired GPU memory utilization (0.92, 58.51 GiB)` —— 根因：上一次 flagtree serve 留下一个**孤儿 `VLLM::EngineCore` 进程**（约 10 GB 显存，占了 GPU 0 长达 26 小时）。它由 bash 脱管 spawn，`pkill -f "port 8033"`、`pkill -f api_server` 都抓不到，只能 `ps aux | grep EngineCore` 按 pid 杀。杀掉后显存释放（861/65536 MiB），relaunch 成功。**教训：杀 serve 后必须 `ps aux | grep -E "api_server|EngineCore"` 兜底检查孤儿进程。**

---

## 6. 与插件项目组适配线的协作问题（⚠️ 需要你拍板）

vllm-plugin-FL 项目组在 **`v0.3.0-dev`** 分支上自己做了 vLLM 0.24.0 适配（在 #252 处与 main 分叉，尚未合入 main）。适配主线：#274（升级 0.20.2→0.24.0）、#294（metax C550 适配）、#308（musa）、#334（mtp）、#338（CUDA stable-ABI wheels）。**也就是说：我们验证用的基线是 main + 我们的补丁（PR #377），项目组的正式适配线是 v0.3.0-dev，两条线。**

我们与 dev 分支的重叠/差异：

| 我们（main + #377） | 项目组（v0.3.0-dev） | 关系 |
|---|---|---|
| `_patch_torch_accelerator()`（在 `__init__.py`） | `accelerator_compat.py` | **功能重复**：两边各写了一份 torch.accelerator 补丁。dev 版更严谨（有 torch<2.9 版本守卫 + 全 API 集；main 上是遗留的最小版，只有 `empty_cache` 一个守卫），但 dev 版的 `reset_peak_memory_stats` 是直接赋值，**缺我们的 try/except 兜底**（torch 2.8 上 mtgpu 显式传 device 会报错）。**注意：torch 2.10+metax 上这些 API 原生齐全（实测）→ 两版 shim 都 no-op，兜底只在 torch 2.8（老 SDK）生效。** |
| `fa_utils.py` 改用 `flag_gems` 的 `reshape_and_cache_flash` | dev 仍用 `ops.reshape_and_cache_flash` | **dev 没处理 empty wheel 场景** → dev 分支 + empty wheel 组合未验证（问题 4 同因，0.20.2 #333 的修法没 upstream 过去） |
| `vllm024_compat.py`（问题 3/5/6 的 4 个补丁） | dev 上不存在 | 项目组没踩到（编译器/验证路径不同）或另有解法 → 我们的 4 个修复要不要 upstream 到 dev，待确认 |
| — | `chunk_delta_h.py` 的 USE_EXP2（0.24.0 上游内核签名新增的参数） | 我们没遇到的坑，验证路径未覆盖 |

**TODO（等你拍板后执行）：**
- [ ] **确认 0.24.0 正式发布线**：main（+ 我们补丁）还是 v0.3.0-dev？如果以 dev 为基线，§4 的验证要在 dev 分支上重验。
- [ ] `_patch_torch_accelerator` 与 `accelerator_compat.py` 去重：保留哪个版本；是否把 reset 的 try/except 兜底 backport 到 dev。
- [ ] 确认 dev 分支在 triton 3.0.0 路径是否缺问题 3/5/6 的修复（serve 冒烟即知）。
- [ ] dev 分支 + empty wheel：`reshape_and_cache_flash` 是否同样报错 → flag_gems 方案是否要 upstream 到 dev。
- [ ] 我们的验证路径补测 USE_EXP2 相关内核（chunk delta，Qwen3-Next/GDN 类模型）。

---

## 7. 遗留事项

- [ ] `setuptools 84.0.0` 超 pyproject `<81` 要求（§2）—— 非致命，保持观察。
- [ ] metax124 容器 pip 命名空间 triton 3.7.1 残留（§5）—— 是否 `pip uninstall` 收敛，待定。
- [ ] 0.24.0 其余后端（nvidia、mthreads、hygon、iluvatar、enflame、sunrise 等）的验证 —— 本报告只覆盖 metax。

---

## 附录 · 验证命令（容器内）

```bash
cd /app/vllm-plugin-FL && PYTHONPATH=/opt/triton:/opt/flagtree \
  nohup /flagos/bin/python -m vllm.entrypoints.openai.api_server \
  --model /data/models/Qwen/Qwen3-4B --port 8031 --enforce-eager --dtype bfloat16 \
  > /tmp/serve-0.24.0.log 2>&1 &

curl -s localhost:8031/v1/completions -H 'Content-Type: application/json' \
  -d '{"model":"/data/models/Qwen/Qwen3-4B","prompt":"The capital of France is","max_tokens":16,"temperature":0}'
```
