# vllm-repack 0.24.0 — 端到端验证报告

> 本文档记录 vllm **0.24.0** 的 repack + 验证活动。0.20.2 的完整 playbook
> 与后端记录见 [`report-vllm-0.20.2.md`](report-vllm-0.20.2.md)（历史 SoT）。
> 标准流程（`empty` 构建 + `+flagos` 后缀 + 单步安装）与 0.20.2 一致，本文
> 只记录 **0.24.0 的增量** 与新的后端验证结果。

## 0. 0.24.0 增量（vs 0.20.2）

| 变化 | 说明 |
|---|---|
| **Rust 组件** | 0.24.0 引入两个独立 Rust 组件，均可忽略（结构性保证，非碰运气）：(1) **`vllm-rs`（Exec 二进制，Rust 前端进程）**——受 `VLLM_USE_RUST_FRONTEND` 控制（`vllm/envs.py:529`，默认 `"0"`），未启用时 `_resolve_rust_frontend_path()` 直接返回 None，进程管理器根本不会被实例化；(2) **`vllm._rust_tool_parser`（PyO3 abi3 扩展）**——唯一引用方是 `RustToolParser`，其唯一子类是 `MinimaxM3ToolParser`，而 `minimax_m3` 在 `tool_parsers/__init__.py` 中 **lazy 注册**（`get_tool_parser` 按名 import，abstract_tool_parser.py:247），即只有服务 MiniMax M3 且开 tool calling 才会 import；缺扩展时抛明确 RuntimeError（非静默错乱）。`setup.py` 顶部无条件 `from setuptools_rust.build import build_rust` → 构建环境必须装 `setuptools-rust>=1.9.0`（否则 `ModuleNotFoundError`）；两个扩展均 `optional=True`，容器无 cargo 时静默跳过，wheel 照常生成。 |
| **empty wheel 绑定 python 版本（重要）** | 0.20.2 的 empty wheel 是 `py3-none-any`（纯 Python，可跨 python 复用——hygon 曾直接复用 mthreads 的 +flagos wheel）。**0.24.0 的 empty wheel 变成 `cp312-cp312-linux_x86_64`**：即使容器无 cargo、Rust 扩展被跳过（wheel 内无任何 `.so`），只要 setup.py 在 `ext_modules` 声明了 Rust 扩展，bdist_wheel 就标 `Root-Is-Purelib: false` + 平台 tag。后果：(a) wheel 按 python 小版本绑定，3.10/3.11 后端（ascend、hygon、kunlunxin、mthreads、sunrise、tsm、cambricon-4.4.3）无法安装 cp312 产物，须各自在自身镜像内构建（`build-and-repack.sh` 本就 per-backend 构建，自洽）；(b) "跨后端复用 +flagos wheel"不再成立，仅同 python 版本间可复用；(c) wheel 无 rust 二进制 → `VLLM_USE_RUST_FRONTEND` 须保持默认 False，走 python fallback。 |
| **build-and-repack.sh** | build deps 安装行新增 `setuptools-rust>=1.9.0` + `wheel`。 |
| **config.yaml 规则** | `remove_torch_chain` + `torch-c-dlpack-ext`；`remove_cuda_only` + `humming-kernels`/`quack-kernels`/`tokenspeed-mla`（0.24.0 cuda.txt 新增的 CUDA 内核库）；`remove_orphaned` 清空（`apache-tvm-ffi` 0.24.0 已不在依赖中）。 |
| **依赖清单** | empty 模式仍走 `requirements/common.txt`（无 torch/triton 声明）；cuda.txt 新增 `tilelang`、`flashinfer`、`nvidia-cutlass-dsl`、`humming-kernels`、`quack-kernels`、`tokenspeed-mla`、`torch-c-dlpack-ext` 等（standard/NVIDIA 构建才相关）。 |
| **xgrammar 0.2.x（重要）** | 0.20.2 解析到 xgrammar 0.1.x，METADATA 无 torch/triton 声明 → 无需 repack。**0.24.0 解析到 xgrammar 0.2.3，声明 `torch>=1.10.0` + `triton`（+ `apache-tvm-ffi`）** → 必须递归 repack。0.20.2 报告的"xgrammar 不需处理"不再成立。 |

**待确认（验证时更新）：**
- [x] empty wheel 缺 rust 二进制时运行时是否正常 —— 结构性确认：wheel 内无任何 `.so`，仅含 python fallback `vllm/tool_parsers/rust_tool_parser.py`；`VLLM_USE_RUST_FRONTEND` 默认 False 走 python 路径。**已验（2026-08-13，metax 单步安装后 serve + 推理正常，见 §2.1）。**
- [ ] `setuptools 84.0.0` 超出 pyproject 要求的 `<81` 是否造成问题（0.20.2 已验证 84 可构建，先保持不动）

---

# 第 2 部分 · 后端验证记录

## 2.1 metax-maca3.7.2.1

- 节点：`metax123`（MACA 3.7.2.x 后端，勿与 maca3.8.1.3 镜像混淆）
- 构建镜像：`flagos-runtime-metax-maca3.7.2.1:2.1.2-build`
- 构建模式：empty（源码构建）

### 构建 + repack

**构建依赖坑（0.24.0 新增）：**
- `setup.py` 顶层无条件 `from setuptools_rust.build import build_rust`（line 21）→ 构建环境缺 `setuptools-rust` 时，metadata 生成直接 `ModuleNotFoundError`（run-1）。已在 `build-and-repack.sh` 构建 deps 里加 `'setuptools-rust>=1.9.0' wheel`。容器无 cargo 不致命（rust 扩展均 `optional=True`，setuptools-rust 会静默跳过）。
- **注意事项：构建源必须是 PyPI sdist，不能是 GitHub 源码包。** 若 tarball 是 GitHub 风格源码包（无 `PKG-INFO`、无 `vllm.egg-info/`），`pip wheel` 会在 `prepare_metadata_for_build_wheel` 阶段报 `LookupError: setuptools-scm was unable to detect version`（run-2）。换用含 `PKG-INFO` + `vllm/_version.py` 的 sdist（md5 `22ae4e41...`）后 metadata 生成通过。**后续后端若再遇 `setuptools-scm was unable to detect version`，先核对 tarball 是否含 `PKG-INFO`。**

**构建结果（2026-08-12）：**
- empty wheel：`vllm-0.24.0+empty-cp312-cp312-linux_x86_64.whl`（7582264 bytes，sha256 `d613ed4f...`）
- repack 输出：**`vllm-0.24.0+flagos-cp312-cp312-linux_x86_64.whl`**（7.5M，`+empty` → `+flagos`，dist-info 目录同名同步改）

**repack 修复（JSON API 解析 bug）：** 首次运行 repack 产出 `repacked_deps: []`（应有三项），根因是两个独立 bug 叠加：
1. **dry-run 主路径失败后静默返回空**——`resolve_dep_versions()` 的 `pip install --dry-run --report` 失败（超时/错误）后 `except: pass` 吞掉原因，直接落入空结果。
2. **fallback `_resolve_pip_version()` 读的是不存在的 URL**——请求 `https://mirrors.aliyun.com/pypi/simple/<pkg>/json`。Aliyun 的 simple 镜像**不提供 PEP-503 JSON API**（实测 numpy/xgrammar/opencv 等所有包均 404），此 fallback 结构性必败。

修复（`repack.py`）：
- 主路径失败原因可见：记录失败尾行/异常类型，回退到 per-dep 时打印 `WARNING: pip resolution returned empty (<原因>)`，不再 `except: pass` 静默吞掉。
- fallback 改用 `pip index versions <pkg> -i <index>`（走 Aliyun 的 HTML simple 索引，可用），解析 `Available versions:` 行取最高匹配 `version_spec` 的版本。

**repack 结果（2026-08-12）：** deps-manifest `removed: {}`、`repacked_deps` 3 项、`retained` 47 项：

| repacked dep | 版本 | 剥离 |
|---|---|---|
| `compressed_tensors` | `0.17.0+flagos` | `torch>=2.10.0` |
| `opencv_python_headless` | `5.0.0.93+flagos`（cp37-abi3-manylinux_2_28） | 两条 `numpy` 声明（faked floor，见 0.20.2 §1.7） |
| `xgrammar` | `0.2.3+flagos`（cp312-cp312-manylinux_2_27） | `torch>=1.10.0` + `triton`（平台标记 x86_64） |

顶层 vllm METADATA 相应把这三个 pin 为 `==X.Y.Z+flagos`（`xgrammar==0.2.3+flagos` 等），单步安装命中 vendor 索引上的 +flagos wheel，不再从 Aliyun 拉回未 repack 版本泄漏 torch/triton。
- METADATA 新观察（0.24.0）：`Requires-Dist: setuptools<81.0.0,>=77.0.3; python_version > "3.11"` —— 单步安装时 pip 会把 venv 的 setuptools（84.0.0）降级到 <81 以满足之，非致命（0.20.2 已验 84 可构建）。

### 安装 + 推理验证

**验证环境：** 节点 `metax123`（MACA 3.7.2.x），容器 `vllm-dbg-metax`（`flagos-runtime-metax-maca3.7.2.1:2.1.2-build`），`/flagos` venv 单步安装 `vllm-0.24.0+flagos-cp312-cp312-linux_x86_64.whl` + `vllm-fl` 插件（`/app/vllm-plugin-FL` 源码树）。serve 需 `PYTHONPATH=/opt/triton:/opt/flagtree`（triton 3.0.0 是 flat layout 侧装）。模型 `Qwen3-4B`，`--enforce-eager --dtype bfloat16`。

**结果：✅ 通过（2026-08-13，两轮）。** `curl /v1/completions`：`"The capital of France is"` → `" Paris. The capital of Germany is Berlin. The capital of Italy is Rome."`（`temperature=0` 与 `0.7` 各一次，Qwen3-4B，`max_tokens=16`）。第一轮用 site-packages 直接改法验证；随后**收敛为插件侧 monkey-patch（vllm wheel 保持 pristine，与 0.20.2 架构一致）**，恢复 4 处 site-packages 为 pristine 后重验通过（见下方 patch 清单）。

**0.24.0 与 0.20.2 的差异（本次安装+推理路径新遇，按 warmup 崩溃顺序）：**

1. **`torch.accelerator` memory API 缺口（0.24 新要求）** — 0.24 无条件调用 `torch.accelerator` 的 `memory_stats`/`memory_reserved`/`empty_cache`/`reset_peak_memory_stats` 等（MemorySnapshot、weight loader）。MACA torch 只实现了 device-management 子集，缺 memory-stats 子集 → 启动即 AttributeError。插件侧 shim（`vllm_fl/__init__.py`）把 `torch.cuda` 等价物绑回 `torch.accelerator`（metax 上 `current_accelerator()=="cuda"`）；`reset_peak_memory_stats(device)` 要 try/except 兜底（mtgpu allocator 初始化前显式传 device 会报错）。

2. **`gdn_linear_attn` 模块搬家** — 0.24 把 `GatedDeltaNetAttention` 从 `vllm.model_executor.layers.mamba.gdn_linear_attn` 移到 `mamba/gdn/base.py`。metax patch 的 import 改 version-gated try/except（`<0.24` 旧路径 → `0.24` 新路径），两个版本的插件代码不用各自维护。

3. **`_load_ptr` 的 constexpr 元素类型（metax triton 3.0.0）** — 0.24 的 BlockTables `_gather_block_tables_kernel` 是唯一把 `tl.int32` 传进 `_load_ptr` 当 `elem_dtype` 的调用方；嵌套 `@jit` 里 dtype 参数以 constexpr 包裹到达，`tl.pointer_type()` 拒绝 constexpr 元素类型（`element_ty is a constexpr.`）。修复：`elem_dtype = elem_dtype.value` 无条件解包。**注意 `isinstance(elem_dtype, tl.constexpr)` 不能当守卫** — triton codegen 调用内建前先解包 constexpr 实参，该判断恒为 False（0.24 上游源码正是这么写的，直接照抄必挂）。

4. **`reshape_and_cache_flash` 空 wheel 阻塞（0.20.2 #333 的重现）** — empty 构建不带编译的 `_C_cache_ops`；0.24 的 metax `fa_utils.py` 把该 op 绑到 `ops.reshape_and_cache_flash` → 首个 attention forward（KV-cache warmup）`AttributeError: '_OpNamespace' '_C_cache_ops' object has no attribute 'reshape_and_cache_flash'`。修复同 0.20.2 #333：改 `from flag_gems import reshape_and_cache_flash`（纯 triton 实现，签名逐参吻合）。**差异点：** 0.20.2 修在 plugin-FL 源码（#333），0.24 的 metax fa_utils 没带上，需在插件侧再打一遍。

5. **penalties 内核的链式布尔（metax triton 3.0.0 codegen）** — `use_rep_penalty or use_freq_penalty or use_pres_penalty` 三连链被拒（"chained boolean operators (A or B or C) are not supported; use parentheses to split the chain"）。操作数是标量加载，加括号 `(A or B) or C` 语义不变。0.24 gpu-worker 采样路径里唯一的链式布尔（已全量检查）。

6. **metax 的 UVA 视图是 CPU-typed 张量（探针确认，crash #4/#5 根因）** — MACA torch 的 `get_cuda_view_from_cpu_tensor` 返回 `device: cpu, is_cuda: False` 的张量（指向 device-accessible 固定内存），而 vllm 的 CUDA 假设是 device-typed 视图。triton 内核可直接当指针读（temperature/min_p/topk 内核无需改），但 torch 用 device tensor 索引 CPU-typed 张量会炸：
   - **crash #4：** `states.py get_top_k_top_p` 用 device 的 `expanded_idx_mapping` 索引 `self.top_k.gpu` → `RuntimeError: indices should be either on cpu or on the same device as the indexed tensor (cpu)`。修：CPU 索引。
   - **crash #5（CPU 索引的次生问题）：** 结果变成 CPU tensor；metax 插件把 `apply_top_k_top_p` 路由到 pytorch fallback（`topk_topp_sampler.apply_top_k_top_p_pytorch`），在 CPU 建 `top_k_mask` 再 gather 到 cuda 的 `logits_sort` → `RuntimeError: Expected all tensors to be on the same device, but got index is on cpu...`（`topk_topp_sampler.py:390`）。修：CPU 索引后 `.to(expanded_idx_mapping.device)` 移回设备。
   - 同类：`pooling_runner.py:40` `prompt_len.gpu[idx_mapping]` → 同样 CPU 索引 + `.to(input_batch.seq_lens.device)`（`seq_lens` 是 device tensor）。
   - 附带确认：`torch.device("metax")` 无效（设备字符串是 `"cuda"`）；`torch.frombuffer` 在 metax torch 无 `device=` kwarg。

**安装侧 patch 清单（已收敛：全部在插件侧，vllm wheel 保持 pristine —— 与 0.20.2 架构一致，4 处 site-packages 已恢复并 md5 验证）：**

| 文件 | 改动 |
|---|---|
| `vllm_fl/__init__.py` | `torch.accelerator` memory API shim（memory_stats/memory_reserved/empty_cache/reset_peak_memory_stats ← torch.cuda 等价物；reset 要 try/except 兜底） |
| `metax/patches/gdn_linear_attn.py` | version-gated import（`<0.24` 旧路径 → `0.24` 新路径） |
| `metax/impl/attention/utils/fa_utils.py` | `reshape_and_cache_flash` → `from flag_gems import ...`（同 0.20.2 #333） |
| `metax/patches/vllm024_compat.py`（新建） | 4 个 vllm 0.24.0 兼容 shim，monkey-patch：`_load_ptr`（`.value` 解包，同步重赋值 `block_table._load_ptr`）、`_penalties_kernel`（链式布尔加括号）、`SamplingStates.get_top_k_top_p` + `PoolingRunner.pool`（UVA CPU 索引 + `.to(device)` 移回设备）。方法 patch 用 `inspect.signature` 版本门控（仅 0.24.0 签名生效），import 全部 try/except 兜底，旧版 vLLM 静默跳过 |
| `metax/patches/__init__.py` | 注册 `from . import vllm024_compat` |

**收敛要点：** 前 3 处是 metax 插件自身代码（0.20.2 就有，0.24 改 version-gate）；后 2 处把原本要直接改 vllm site-packages 的 4 个文件变成插件内 monkey-patch。`_load_ptr`/`_penalties_kernel` 是模块级 `@triton.jit` 函数 → 重新定义同签名内核 + 重赋值模块全局；`_load_ptr` 被 block_table 以 `from buffer_utils import _load_ptr` 绑定 → 必须同步重赋值 `block_table._load_ptr`。验证：独立进程绑定检查 + 恢复 pristine site-packages 后完整 serve 推理（EngineCore 子进程走插件加载路径，patch 生效）。

**验证命令（容器内）：**
```bash
cd /app/vllm-plugin-FL && PYTHONPATH=/opt/triton:/opt/flagtree \
  nohup /flagos/bin/python -m vllm.entrypoints.openai.api_server \
  --model /data/models/Qwen/Qwen3-4B --port 8031 --enforce-eager --dtype bfloat16 \
  > /tmp/serve-0.24.0.log 2>&1 &
curl -s localhost:8031/v1/completions -H 'Content-Type: application/json' \
  -d '{"model":"/data/models/Qwen/Qwen3-4B","prompt":"The capital of France is","max_tokens":16,"temperature":0}'
```

## 2.2 metax-maca3.8.1.3（TODO · 四环境矩阵）

**背景：** metax 有两个后端（3.7.2.x 与 3.8.1.x），每后端两套编译器（FlagTree 默认 / Triton 侧装），共 **2 后端 × 2 编译器 = 4 种环境**。§2.1 只覆盖了其中一种。**默认编译器是 FlagTree，而 §2.1 走的是 `/opt/triton`（3.0.0）—— 默认路径反而未验证。**

**环境分布：**

| 环境 | 节点 | torch | 编译器 | 状态 |
|---|---|---|---|---|
| 3.7.2.1 + FlagTree | metax123 | 2.8.0 | flagtree **0.6.1+metax3.6**（triton 3.6.0 基座，最新版，见 §2.2.1） | ✅ 已验（2026-08-14） |
| 3.7.2.1 + FlagTree（SDK 对齐版） | metax123 | 2.8.0 | flagtree 3.1.0+metax3.7.2.0 | ❌ 已弃用（2026-08-14 决定，见 §2.2.1） |
| 3.7.2.1 + Triton | metax123 | 2.8.0 | triton 3.0.0+metax3.7.2.0 | ✅ 已验（§2.1，2026-08-13） |
| 3.8.1.3 + FlagTree | metax124 | 2.10.0 | flagtree 0.6.1+metax3.6 | ✅ 已验（2026-08-15，见 §2.2.2） |
| 3.8.1.3 + Triton | metax124 | 2.10.0 | triton 3.6.0+metax3.8.1.0 | ✅ 已验（2026-08-15，见 §2.2.2） |

**顾虑：** §2.1 的修复大多针对 triton 3.0.0 特有行为（链式布尔、`_load_ptr` constexpr 元素类型、UVA CPU-typed 视图），3.8.1.3 是 triton 3.6.0 + flagtree 0.6.1，编译器行为可能不同（kunlunxin FlagTree 0.6.1 编译失败、sunrise FlagTree decode 卡死切 triton 均为先例）→ 插件侧 shim（§2.1 patch 清单）需逐环境重验，必要时按编译器 version-gate。**§2.2.1 已证 triton 3.6.0 基座（flagtree 0.6.1）上现有 shim 全部安全 no-op/兼容。**

**TODO：**
- [x] 3.7.2.1 + FlagTree 冒烟（serve + 推理）—— 用**最新版 0.6.1+metax3.6** 验证（§2.2.1），并作为默认编译器安装闭环
- [x] 预检 metax124：3.8.1.3 runtime（`:2.1.2` / `:2.1.2-build`，已有镜像）容器可启动（docker run + device 可见）；容器内两套编译器版本确认（`compiler` 函数 + `/opt/flagtree` + `/opt/triton`）；是否有 vllm 0.24.0 安装/验证痕迹
- [x] 3.8.1.3 + FlagTree 冒烟（2026-08-15，见 §2.2.2）
- [x] 3.8.1.3 + Triton 冒烟（2026-08-15，见 §2.2.2）
- [x] 每环境记录：编译器行为差异、插件 shim 是否需 version-gate/条件编译（见 §2.2.2）
- [x] 决定 flagtree 版本（2026-08-14）：**弃用 3.1.0，metax 全线用 0.6.1+metax3.6**。0.6.1 在 3.7.2.1 老 SDK 上零新增 patch 直接可用（§2.2.1），无需为 3.1.0 保留 patch #5/#6（triton 3.6.0 基座自带 kwarg + knobs）。configs.yaml 的 maca3.7.2.1 flagtree pin 已改为 0.6.1+metax3.6

### 2.2.1 metax123 3.7.2.1 + FlagTree 0.6.1（最新版，2026-08-14）

**背景：** 默认编译器路径（flagtree 3.1.0+metax3.7.2.0，SDK 对齐版）在 vllm 0.24.0 上有两个 API 缺口：`triton.jit` 缺 `do_not_specialize_on_alignment` kwarg（minimax_m3 `index_topk` 无条件 import）、`triton` 缺 `knobs`（jit_monitor 无条件 import）。插件侧已加 patch #5/#6 修掉（version-gated，triton 3.0.0 上 no-op），但用户判断 **flagtree 团队无 MACA SDK 版本对齐意识** → 直接试最新版 **0.6.1+metax3.6**（triton 3.6.0 基座，对齐 torch 2.10/MACA 3.8.1.x），看老 SDK 上能否直接跑。

**安装：** 从 `flagos-pypi-hosted` 拉 `flagtree-0.6.1+metax3.6-cp312-cp312-linux_x86_64.whl`（421.7 MB，`https://resource.flagos.net/repository/flagos-pypi-hosted/simple/`，Nexus URL 见 `flagtree-wheel.yml:130`，非自造主机名），`pip install --no-deps --target /opt/flagtree-061` 侧装。**坑：** 该 wheel 的 triton 报 `__version__ = '3.6.0'`（不是 0.6.1），且 `knobs=True`、`do_not_specialize_on_alignment` 存在 → 插件 patch #5/#6 自动 no-op（version-gate 生效）。

**结果：✅ 通过（2026-08-14）。** serve 端口 8032（`PYTHONPATH=/opt/flagtree-061`，其余命令同 §2.1：Qwen3-4B、`--enforce-eager --dtype bfloat16`），startup 干净无 crash，`/v1/completions` 输出与 triton 3.0.0 完全一致：`"The capital of France is"` → `" Paris. The capital of Germany is Berlin. The capital of Italy is Rome."`。**零新增 patch** —— §2.1 的 6 个 shim 在 triton 3.6.0 基座上全部兼容（triton 3.0.0 特有的 4 个 bug 在 3.6.0 上不存在，patch 应用后无害）。

**结论：**
- flagtree 0.6.1+metax3.6（为 3.8.1.x 构建）在 **3.7.2.1 老 SDK 上直接可用**，佐证"flagtree 无需按 MACA SDK 对齐版本"的判断。
- triton 3.6.0 基座解决了 triton 3.0.0 上的全部 4 个编译/UVA 问题（链式布尔、constexpr 元素类型、UVA CPU-typed 视图）——若 3.8.1.3 两环境也走 0.6.1/3.6.0，§2.1 的 shim 可能整体可以收窄。
- **决策（2026-08-14）：弃用 3.1.0，metax123 容器 `/opt/flagtree` 已替换为 0.6.1+metax3.6**——默认编译器路径（`PYTHONPATH=/opt/flagtree`，无覆盖）serve + 推理已验证（本节上文）；configs.yaml 的 maca3.7.2.1 flagtree pin 相应改为 `0.6.1+metax3.6`。为 3.1.0 写的插件 patch #5/#6（`do_not_specialize_on_alignment` + `knobs`）随 3.1.0 弃用而不再需要，但保留无害（version-gated，triton 3.6.0 上自动 no-op）。

### 2.2.2 metax124 3.8.1.3（四环境矩阵收官，2026-08-15）

**预检（环境盘点）：** 容器 `vllm-dbg-metax3813`（宿主机 metax124），8×C550 可见。环境：
- torch **2.10.0+metax3.8.1.0**，vllm **0.24.0+flagos**（`/vllm-repack` 中，`pip show vllm` 可查，`python -c "import vllm; vllm.__version__"` 报 0.24.0+flagos）
- `/opt/flagtree` = **0.6.1+metax3.6**（triton 3.6.0 基座）、`/opt/triton` = **3.6.0+metax3.8.1.0**（侧装）；`compiler` 函数两个都可用
- pip 命名空间里的 triton = **3.7.1**（源码安装残留，serve 用 `/opt/triton` 的 PYTHONPATH 显式覆盖，**实际生效的是 3.6.0**——见下方坑）
- 插件 @ **43edeb6（main）** + 本机未提交的 0.24.0 shim（`vllm024_compat.py` 等，provenance 见 §2.3）

**FlagTree 冒烟（默认编译器路径）：** 端口 8033，`PYTHONPATH=/opt/flagtree` 前置，其余命令同 §2.1（Qwen3-4B、`--enforce-eager --dtype bfloat16`）。startup 干净无 crash，`/v1/completions` 输出与 triton 3.0.0 / 3.7.2.1 环境完全一致：`"The capital of France is"` → `" Paris. The capital of Germany is Berlin. The capital of Italy is Rome."`。**零新增 patch** —— §2.1 的 6 个 shim 在 3.6.0 基座上全部兼容（与 §2.2.1 结论一致）。

**Triton 冒烟：** 端口 8034，`PYTHONPATH=/opt/triton` 前置（该 serve 由前序会话 2026-08-14 启动，本次直接复用）。输出与 FlagTree 冒烟完全一致。

**坑（已解决）：GPU 显存碰撞。** flagtree serve 二次启动时 startup 报 `ValueError: Free memory on device cuda:0 (2.02/63.59 GiB) on startup is less than desired GPU memory utilization (0.92, 58.51 GiB)` —— 根因：上一次 flagtree serve 的 **孤儿 `VLLM::EngineCore` 进程**（bash -lc 脱管 spawn，`pkill -f "port 8033"` / `pkill -f api_server` 均抓不到，需 `ps aux | grep EngineCore` 按 pid 杀）独占 GPU 0 约 10GB 长达 26h。`kill -9` 该 pid 后显存释放（861/65536 MiB），relaunch 成功。**教训：杀 serve 后必须 `ps aux | grep -E "api_server|EngineCore"` 兜底，孤儿 EngineCore 只按 pid 杀。**

**每环境记录（四环境矩阵收官）：**
- 编译器行为差异：**3.8.1.3 两环境与 3.7.2.1 两环境输出完全一致，零新增 patch**。triton 3.0.0 特有的 4 个编译/UVA 问题（链式布尔、`_load_ptr` constexpr 元素类型、UVA CPU-typed 视图）在 3.6.0 基座上不存在；§2.1 的 shim 全部安全 no-op/兼容 —— 与 §2.2.1 的推断一致，**无需 per-环境 version-gate**。
- **四环境矩阵全部 ✅**（3.7.2.1×2 + 3.8.1.3×2）：vllm 0.24.0+flagos 在 metax 全线的默认编译器路径（FlagTree 0.6.1）与 Triton 侧路径均已 serve + 推理验证。
- 残留观察（不阻塞）：pip 命名空间 triton 3.7.1 与 `/opt/triton` 3.6.0 不一致，靠 PYTHONPATH 显式覆盖；若后续有人不设 PYTHONPATH 直接 `import triton` 会踩 3.7.1。可考虑在容器里 `pip uninstall triton` 收敛，待用户判断。

## 2.3 插件项目组自身的 0.24.0 适配（v0.3.0-dev 分支，⚠️ 与 #377 重叠）

**背景：** vllm-plugin-FL 项目组在 **`v0.3.0-dev`** 分支自行做 vLLM 0.24.0 适配，与 main 在 #252 处**分叉、尚未合入 main**。适配主线：#274（`upgrade: vllm 0.20.2 -> 0.24.0`）、#294（`adapt(metax): MetaX C550 backend adaptation for vLLM 0.24.0`）、#308（musa MTT S5000）、#334（mtp in 0.24.0）、#338（CUDA stable-ABI wheels）、#346/#348。**这意味着 §2.1 验证用的插件基线（main + PR #377 patch）与项目组的正式适配线（v0.3.0-dev）是两条线。**

**与 §2.1（main + #377）的重叠/差异：**

| 我们（#377，main） | 项目组（v0.3.0-dev） | 关系 |
|---|---|---|
| `vllm_fl/__init__.py` `_patch_torch_accelerator()` | `patches/accelerator_compat.py`（dev：torch<2.9 版本守卫 + hasattr 权威守卫 + 全 API 集，2026-08-15 拉取核验 ✓；main 上为遗留最小版：仅 `empty_cache` hasattr 守卫，#241 引入/#300 加头） | **功能重复**（两分支各自 patch torch.accelerator）。dev 版本更严谨（有版本守卫），但 `reset_peak_memory_stats` 是直接 setattr，**缺 try/except 兜底**（mtgpu allocator 初始化前显式传 device 报错，§2.1 差异 1）。**注意：torch 2.10+metax 上全部 API 原生存在（metax124 实测）→ 两 shim 均 no-op，reset 兜底只在 torch 2.8（3.7.2.1）生效** |
| `fa_utils.py` → `from flag_gems import reshape_and_cache_flash`（empty wheel 无编译 `_C_cache_ops`） | dev `fa_utils.py` 仍 `ops.reshape_and_cache_flash` | **dev 未处理 empty wheel 场景** → dev 分支 + empty wheel 组合未验证（§2.1 crash #4 同因，0.20.2 #333 方案未 upstream） |
| `patches/vllm024_compat.py`（_load_ptr constexpr / _penalties_kernel 链式布尔 / get_top_k_top_p + pool UVA，triton 3.0.0 特有） | dev 上**不存在** | 项目组未踩（编译器/验证路径不同）或另有解法 → 我们的 4 修复是否需 upstream 到 dev 待确认 |
| — | `chunk_delta_h.py` USE_EXP2（#294；0.24.0 上游 kernel 签名新增 `USE_EXP2: tl.constexpr`） | 我们未遇到的坑，§2.1 验证路径未覆盖 |

**TODO：**
- [ ] 与项目组确认 0.24.0 正式发布线：main（+ 我们 patch）还是 v0.3.0-dev？（后者已含 #274/#294/#308/#334/#338，未合入 main）
- [ ] 若以 v0.3.0-dev 为基线 → §2.1 验证（main+#377）需在 dev 分支**重验**；§2.2 四环境矩阵的插件基线相应换成 v0.3.0-dev
- [ ] `_patch_torch_accelerator` 与 `accelerator_compat.py` 去重：保留哪个版本；是否把 reset_peak_memory_stats 的 try/except 兜底 backport 到 dev 版本
- [ ] 确认 dev 分支在 triton 3.0.0 路径是否缺 _load_ptr/_penalties_kernel/get_top_k_top_p/pool 修复（serve 冒烟即知）
- [ ] dev 分支 + empty wheel：`ops.reshape_and_cache_flash` 是否报 AttributeError（同 §2.1 crash #4）→ flag_gems 方案是否需 upstream 到 dev
- [ ] 我们的验证路径补测 USE_EXP2 相关内核（chunk delta，Qwen3-Next/GDN 类模型）

---

# 第 3 部分 · 自动化边界 + ADR

_TBD_
