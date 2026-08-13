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
- [x] empty wheel 缺 rust 二进制时运行时是否正常 —— 结构性确认：wheel 内无任何 `.so`，仅含 python fallback `vllm/tool_parsers/rust_tool_parser.py`；`VLLM_USE_RUST_FRONTEND` 默认 False 走 python 路径。运行时行为待安装后验证。
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

_TBD_

---

# 第 3 部分 · 自动化边界 + ADR

_TBD_
