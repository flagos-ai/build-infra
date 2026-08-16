# megatron-core（Megatron-LM-FL fork）hygon25 端到端验证 — 技术发现与缺口

## Status

**两个训练入口均在 hygon25（DTK 26.04）上通过端到端验证（exit 0）：**

| 验证形态 | 内容 | 结果 |
|---|---|---|
| wheel-only 训练循环 | `examples/run_simple_mcore_train_loop.py`（仅依赖 wheel 内的 megatron.core），TP=2，5 iter，mock data，含 checkpoint 保存/加载 | ✅ exit 0 |
| 完整训练服务 | `pretrain_gpt.py`（megatron.training + repo checkout），5 iter，mock data | ✅ exit 0，loss 9.1310 → 8.6514 |

上表为默认编译器（flagtree）基线。**vendor triton 复跑**（见 §2.1）下两种形态均通过，且不再需要 jit 补丁与 `--disable-jit-fuser`：完整训练服务 loss 9.1295 → 8.8622。

本报告只记录**可复现的技术发现与缺口**（代码级缺陷、未声明依赖、平台移植性、工具链限制），不含瞬时错误与一次性环境故障。

## 打包背景

**当前 wheel 打包范围继承上游，不含训练包——这是本报告若干发现的根因。**

**"上游"所指（本报告约定，避免歧义）：** 本报告涉及两级仓库——**代码来源的上游 = NVIDIA 的 ADLR/Megatron-LM**（megatron 代码的原始出处，fork 通过同步 PR 引入）；**提交 PR / 反馈缺陷的目标 = 本 fork flagos-ai/Megatron-LM-FL**（build-infra 工作直接面向的仓库）。下文"上游"均按此区分：涉及代码继承时为 ADLR/Megatron-LM，涉及提交与反馈时为 flagos-ai/Megatron-LM-FL。

- 打包入口是仓库根 `pyproject.toml` 的 `[tool.setuptools.packages.find]`，include 范围**继承自 NVIDIA 上游 ADLR/Megatron-LM**（fork 通过同步 PR #34 "Synchronization with Megatron-LM Core 0.17.0" 引入上游 0.17.0 后未改动），仅含 `megatron.core` 与 `megatron.plugin` 两个包。
- `megatron.training` / `megatron.legacy` / `megatron.inference` / `megatron.post_training` / `megatron.rl` **均不在 wheel 中**。
- **后果:** 完整训练服务（`pretrain_gpt.py`）依赖 `megatron.training`，无法用 wheel 直接验证——这是报告"完整训练服务"一栏用 repo checkout 的原因，也是 §1.1（`megatron.core` 内部 import `megatron.training` 失败）的直接诱因。
- **性质:** 非打包实现错误（fork 只是继承了上游的范围），但属于**真实范围缺口**——对"应用镜像 = 单步安装 wheel 即可用"的交付形态而言必须关闭。
- **方向（待定案）:** 扩大打包范围，把 `megatron.training` / `megatron.legacy` 纳入 wheel（pyproject include 已改，未提交），是否进一步纳入 `megatron.inference` / `megatron.post_training` / `megatron.rl`（全包，应用场景归并进一个 wheel）在决策中。

**Date:** 2026-08-12 ~ 2026-08-13
**Platform:** hygon25（Hygon BW1000 8× HCU，DTK 26.04），镜像 `flagos-runtime-hygon-dtk26.04:2.1.2`，Python 3.10.20，torch 2.9.0+das.opt1.dtk2604
**安装形态:** Megatron 打包（`packaging/megatron/builder/`）产出的 `megatron-core==0.17.1+flagos` wheel，`pip install`（无 `--no-deps`）

---

## 1. 代码级缺口

### 1.1 megatron.core 内不可用的 import：`megatron.training`（已修复，PR #105 已提交）

**位置:** `megatron/plugin/utils.py:30` — `is_built_on_zero_rank()`

**缺陷:** `from megatron.training import get_args` 位于 try/except 之外（代码注释本身即承认 "We should not depend on get_args in megatron core, the args belong to training."）。`megatron.training` **不在 wheel 中**（wheel 只打包 `megatron.core`），因此任何仅使用 wheel 的消费方在 `megatron.core` 内部路径触发此函数时，import 直接抛 `ModuleNotFoundError`，且 try/except（注释 "for unit tests"）形同虚设。

**影响路径（实测）:** `megatron/core/datasets/blended_megatron_dataset_builder.py:19` 模块级导入 `is_built_on_zero_rank`，在 392/407/535/551 四处调用 → wheel-only 的数据集构建路径必然触发。

**修复:** 将 import 移入 try 块（1 行改动）。已在 wheel、repo 副本、本地仓库三处应用，并经 wheel-only 训练循环重跑验证（exit 0）。

### 1.2 未声明的运行时依赖：psutil（NVIDIA 上游代码缺口）

**位置:** `megatron/core/dist_checkpointing/strategies/filesystem_async.py:42-47, 674-676`

**缺陷:** psutil 通过 `try/except ImportError` 导入并置 `HAVE_PSUTIL` 标志；异步 `FileSystemWriter` 的 worker 线程调用 `_process_memory()`（line 674），在 `HAVE_PSUTIL=False` 时抛
`RuntimeError("psutil is not installed, ...")`。即：**psutil 被实际使用，却既不在 wheel METADATA 的 `Requires-Dist` 中，也不在 runtime 镜像内**（均实测确认）。wheel 的 `Requires-Dist` 仅 `torch>=2.6.0` / `numpy` / `packaging>=24.2` + optional extras。

**触发条件（实测）:** 任何 wheel-only 消费方在 checkpoint 保存时使用异步策略即触发（`Worker failure: ... psutil is not installed`）。修复方式是额外 `pip install psutil`（7.2.2）——但这是对 "单步安装即可用" 目标的破坏，属真实的 wheel 依赖缺口。已提交至本 fork（flagos-ai/Megatron-LM-FL，PR #106：把 psutil 纳入 `pyproject.toml` 的 `dependencies`）。

### 1.3 `jit_fuser` 在模块 import 期绑定 `torch.compile`，`--disable-jit-fuser` 无法拦截（时序缺陷）

**位置:** `megatron/core/jit.py:16-33`

**缺陷:** `enable_jit_fuser()` 在**模块 import 时即执行**（line 33 模块级调用），把全局 `jit_fuser` 绑定为 `torch.compile`；`bias_gelu`/`bias_swiglu` 的 `@jit_fuser` 装饰在 import 期随之生效。`--disable-jit-fuser` 在 args 解析之后才调用 `disable_jit_fuser()` 翻转全局，**晚于装饰器生效点**，无法阻止训练 warmup 期的 `torch.compile` 执行。

**DCU 上的后果:** warmup 期 `torch.compile` 触发 triton HCU 编译，而本镜像的 clang 无法编译 HCU kernel（见 §2.1）→ HSACOError。任何依赖 `--disable-jit-fuser` 的 DCU 使用方都会踩到。修复方向：`jit_fuser` 改为惰性装饰（或 `enable_jit_fuser` 默认 no-op，由训练入口显式开启），而非 import 期绑定。

### 1.4 masked softmax fusion 默认开启且依赖 CUDA-only 扩展（平台移植性缺口）

**位置:** `megatron/core/fusions/fused_softmax.py:346-360`

**缺陷:** fused softmax 路径的 `get_batch_per_block()` 内 `import scaled_masked_softmax_cuda`（CUDA-only 编译扩展，DCU 上不存在）。而 `masked_softmax_fusion` 默认开启（`--no-masked-softmax-fusion` 为 store_false 开关），因此 DCU 上**必须显式传 `--no-masked-softmax-fusion`**，否则 `ModuleNotFoundError: No module named 'scaled_masked_softmax_cuda'`。

**性质:** megatron 默认假设其 fused kernel 一定可用；对非 CUDA 平台，这些默认值需要逐一显式关闭——平台移植性的普遍缺口，非 hygon 独有。

---

## 2. 工具链 / 环境缺口（可复现）

### 2.1 编译器可用性：flagtree 无法编译 HCU kernel，vendor triton 可用（编译器 mask 表）

**结论：** 运行时镜像默认的 flagtree 编译器在 hygon（DTK 26.04）上**不可用**；vendor triton（`compiler triton` 切换至 `/opt/triton`）**可用**。

| 编译器 | 版本 | HCU kernel 编译 | 结论 |
|---|---|---|---|
| flagtree | 3.6.0 | ✗ `make_amdgcn()` 调 clang-17 子进程，7 个 HCU `-mllvm` flags 中 5 个被拒 → clang 静默退出 0 但无产物 → 误导性 `HSACOError("File operation failed: ...")` | **屏蔽** |
| vendor triton | 3.3.0 | ✓ `make_amdgcn()` 用 `llvm.translate_to_asm()` 直接出码，无 clang 子进程 → 正常产出 `.amdgcn` | **交付** |

- **性质:** flagtree 特有缺陷（`_get_clang_args()` 空字符串 clang-arg + 镜像 clang 不接受 `-mllvm` flags），非平台通用问题；vendor triton 路径不经过 clang。
- **验证面:** 按平台验证规则，每个后端 × 两个编译器都要验证；不能用的编译器在交付镜像中屏蔽（不设为默认/不装）。
- **影响:** flagtree 作为 hygon runtime 镜像的默认编译器属错误默认，需在 runtime 镜像层修正（默认改为 vendor triton 或移除 flagtree）。
- **验证时手动切换方法（镜像内置 `compiler` 函数，来自 BASH_ENV）：** `compiler triton`；无该函数时：`export PYTHONPATH="/opt/triton:$(printf %s "${PYTHONPATH}" | tr ':' '\n' | grep -v '^/opt/flagtree' | paste -sd: -)"`。

### 2.2 `helpers_cpp*.so` 的查找契约：wheel 与源码树混用

- wheel 的编译扩展 `helpers_cpp*.so` 位于 site-packages；而 `compile_helpers()`（FlagScale patch）在**源码树**中查找该 `.so`。
- 因此 "repo checkout + 已安装 wheel" 的验证形态（完整训练服务）需先把 wheel 内的 `.so` 植入源码树。
- 对 app 镜像**无影响**（wheel 自带 `.so`，单步安装即完整）；此缺口只影响仓库与 wheel 混用的验证/开发路径。

### 2.4 venv 缺 `python3-config`（2026-08-16 实测）

**发现（运行 #2，06:04:18 rc=1）：** venv `/flagos/bin` **缺 `python3-config` 符号链接**。`compile_helpers()`（`megatron/core/datasets/utils.py`，带 FlagScale 来源标注的 fork 补丁）执行 `subprocess.check_output(["python3-config", "--extension-suffix"])` 抛 `FileNotFoundError: 'python3-config'`，`pretrain_gpt.py` 在数据集构建 import 期即挂。该函数只在 wheel 已带预构建 `helpers_cpp{ext_suffix}.so` 时提前 return 跳过 make——但仍需 python3-config 算后缀。uv 托管的 Python 在 `/root/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/bin/` 下自带该二进制。修复（仅诊断用软链，非交付方案）：`ln -sf .../python3-config /flagos/bin/python3-config`，`--extension-suffix` 实测输出 `.cpython-310-x86_64-linux-gnu.so`。

**对交付的启示（已落地，2026-08-16）：** 修复方向 = `compile_helpers()` 改用 `sysconfig.get_config_var("EXT_SUFFIX")`（标准库，任何 Python 环境都有），替代 `subprocess.check_output(["python3-config", ...])`。
- **准备一（PR 已提交）：** flagos-ai/Megatron-LM-FL PR [#112](https://github.com/flagos-ai/Megatron-LM-FL/pull/112)（与 psutil PR #106 / tensorboard 同类的上游修复）。
- **准备二（build-infra 兜底，已落地）：** wheel 是 build-infra 自产（`packaging/megatron/builder/Containerfile`），沿用现有 on-the-fly patch + grep gate 模式（同文件 requires-python 补丁）新增 `packaging/megatron/builder/patch-compile-helpers-sysconfig.py`，在 wheel 构建时对 checkout 打同样的 sysconfig 补丁。脚本幂等且自 gate：已是 sysconfig 形式 → no-op（PR #112 合并后自动跳过）；仍是 python3-config 形式 → 就地替换；源码演进（两种形式都找不到）→ exit 1 硬失败，补丁不可能静默失效。三状态逻辑已本地验证（对 origin/main 的 utils.py 实测 patch / no-op / 演进三例全过）。两路最终都落成同一段代码形态，不依赖 MLF merge 节奏。诊断软链（`/flagos/bin/python3-config` → uv python）仅容器现场用，非交付方案。

### 2.3 DTK 环境注入：镜像已内置

- 运行时镜像已内置 DTK 环境：经 bash 运行的命令（含非交互）可直接 `import torch`，无需手动 `source /opt/dtk-26.04/env.sh`（实测：容器内非登录 `bash -c '/flagos/bin/python -c "import torch"'` 直接成功，torch 2.9.0）。
- **注意事项：** 进程不经 bash 直接启动（如 `docker exec` 直接执行 python）时 DTK 环境缺失 → `libgalaxyhip.so.5` 报错；此时需显式 `source /opt/dtk-26.04/env.sh`。E2E 脚本采用该防御写法。

---

## 3. 依赖面结论

**METADATA 声明的依赖面 ≠ 真实运行时依赖面。** psutil（§1.2）被异步 checkpoint 策略实际使用但未声明——任何 wheel-only 消费方保存 checkpoint 即缺。对依赖处理（repack）而言，除 torch 外还需把 psutil 纳入运行时依赖检查（或反馈至本 fork flagos-ai/Megatron-LM-FL 补声明）。

---

## 4. 可复现的运行参数基线

DCU 上完整跑通 megatron 训练的最小 flags / 容器配置（逐项均有失败→修复的实证）：

| 参数 / 配置 | 原因 |
|---|---|
| `--no-masked-softmax-fusion` | §1.4：fused 路径 import CUDA-only 扩展 |
| `--disable-jit-fuser` | **仅 flagtree 编译器下需要**（§1.3 + §2.1）；vendor triton 下已不需要（复跑验证） |
| `--no-persist-layer-norm` / `--no-gradient-accumulation-fusion` | 相应 fused kernel 在 DCU 上不可用的显式关闭 |
| `--attention-backend unfused` | DCU 上无 fused attention 后端 |
| `--transformer-impl local` | 不依赖 TransformerEngine（DCU 无对应构建） |
| `--shm-size=8g`（docker run） | torch multiprocessing 需大于容器默认 64MB 共享内存 |
| `source /opt/dtk-26.04/env.sh`（防御性；经 bash 运行非必需） | §2.3：镜像已内置 DTK 环境；仅非 bash 直启进程需显式 source |

**可复现配方:** `/tmp/hygon25-megatron-e2e.sh`（节点上执行，两阶段：wheel-only 训练循环 / 完整训练服务）。

---

## 5. 结论与后续

- **E2E 故事闭环**：wheel（Megatron 打包产物）→ 单步安装（无 `--no-deps`）→ 端到端训练，在 hygon25 上全部实证通过。
- **打包范围缺口（待定案）**：见"打包背景"——wheel 不含 `megatron.training` 导致完整训练服务无法用 wheel 直接验证；扩大范围（training+legacy 或全包）后需重建 wheel 并以"单步安装 + 直接跑 `pretrain_gpt.py`"（无需 repo checkout）重新验证。
- **已提交至本 fork（flagos-ai/Megatron-LM-FL）**：§1.1 修复 → PR [#105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105)；§1.2 依赖声明 → PR [#106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106)。
- **待反馈至本 fork（flagos-ai/Megatron-LM-FL）**：§1.3 jit_fuser import 期绑定时序、§1.4 fused kernel 默认开启的平台假设。
- **相关文档**：`packaging/megatron/builder/report-megatron-0.17.1.md`（构建与依赖面；repack facility 已于 2026-08-14 移除，依赖处理不再单独成报告，其要点并入 builder report §1/§3）。
