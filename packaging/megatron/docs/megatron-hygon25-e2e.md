# Megatron-LM-FL hygon25 E2E 验证报告

**验证环境:** hygon25（Hygon BW1000 8× HCU，DTK 26.04），runtime 镜像
`flagos-runtime-hygon-dtk26.04:2.1.2`，Python 3.10.20，torch
2.9.0+das.opt1.dtk2604。
**安装形态:** Megatron 打包（`packaging/megatron/builder/`）产出的
`megatron-core` wheel，`pip install`（无 `--no-deps`）。
**验证周期:** 2026-08-12 ~ 2026-08-17。

**术语约定:** 本报告涉及两级仓库——代码来源的上游 = NVIDIA 的
ADLR/Megatron-LM（megatron 代码的原始出处，fork 通过同步 PR 引入）；
提交 PR / 反馈缺陷的目标 = 本 fork flagos-ai/Megatron-LM-FL。下文"上游"
均按此区分：涉及代码继承时为 ADLR/Megatron-LM，涉及提交与反馈时为
flagos-ai/Megatron-LM-FL。

**缩写:** TE = TransformerEngine；THD = 打包序列（THD）格式；FA = flash
attention。

本报告只记录**可复现的技术发现与缺口**（代码级缺陷、未声明依赖、
平台移植性、工具链限制），不含瞬时错误与一次性环境故障。

## 0. Summary

**结论：** 四个场景全部打通。training / post_training / inference 由全范围
wheel 单步安装直跑，均 exit 0，并已在 vendor triton 3.5.1（PR #404 升级后）
下全部复验通过（2026-08-17）；rl 场景耗时最长——未声明依赖与厂商包问题逐一解决后，全链路首次跑通 exit 0。

| 场景 | 状态 | 一句话事实 |
|---|---|---|
| training | ✅ 通过 | 全范围 wheel 单步安装直跑 `pretrain_gpt.py`，exit 0 |
| rl | ✅ 通过 | 全链路 exit 0；前提 = 补装未声明依赖（§5.1）+ vendor TE（§5.4） |
| post_training | ✅ 通过 | driver 全 import + `simple_generate`，exit 0；前提 = ad-hoc 装 modelopt（§1.3.3） |
| inference | ✅ 通过 | `StaticInferenceEngine(legacy=True)`，3 请求 × 8 tokens，exit 0 |

**教训清单**：

1. **打包范围必须覆盖 entry point 与顶层脚本**——否则完整服务无法单步安装即用。已由全范围打包关闭（§1.1，PR #107）。
2. **未声明运行时依赖是主要耗时项**——psutil / tensorboard / wandb 等被实际使用却未声明（§1.2、§5.1）。psutil 已补声明（PR #106）；RL 清单待反馈。
3. **vendor 包不可信，问题分四类**——元数据、包间版本失配、平台覆盖、源码杂质；逐包 repack 修正并记录（§1.3）。
4. **平台移植性默认值**——fused kernel 默认开启、jit_fuser import 期绑定，
   非 CUDA 平台需显式关闭（§1.4）。待反馈。
5. **工具链按平台验证**——flagtree 曾误判"无法编译 HCU kernel"（旧容器缺
   DTK LLVM 包）；编译器结论不跨版本/平台移植，每后端 × 每编译器实测（§1.5）。
6. **venv 缺 python3-config** 使数据集构建 import 期挂（§2.1）。已落地
   sysconfig 兜底 + PR #112。
7. **datasets/pyarrow 版本对不兼容**——5.0.1 写、≤25 读崩（§5.2）。已规避；
   CI 需固定实测版本对。
8. **tokenizer 无 eos** 使轨迹准备 TypeError（§5.3）。数据层声明即解决。
9. **RL 训练 forward 强制 TE**——local 不支持 THD 打包序列（§5.4）。hygon
   已跑通；无 vendor TE 平台待反馈。
10. **flash_attn 版本串三处不一致**致 dynamic 引擎断言失败（§5.5）。repack
    三处字符串一致即解决。
11. **modelopt 未入镜像**，post_training 靠 ad-hoc 补装，违反交付目标（§1.3.3）。纳入镜像与否待决策。

## 1. 全局性问题

### 1.1 打包范围不完整（entry point / 顶层脚本）

- **现象:** wheel 打包范围继承上游，仅含 `megatron.core` 与
  `megatron.plugin`，`megatron.training` / `legacy` / `inference` /
  `post_training` / `rl` 与顶层入口（`pretrain_gpt.py` 等）均不在其中——
  完整训练服务无法"单步安装 wheel 即用"，必须 repo checkout；且
  `megatron.core` 内部路径触发 `from megatron.training import get_args`
  （`megatron/plugin/utils.py:30`，import 在 try/except 之外）时直接抛
  `ModuleNotFoundError`——wheel-only 的数据集构建必然触发。
- **原因:** include 范围继承自 NVIDIA 上游 ADLR/Megatron-LM 的
  `pyproject.toml`（同步 PR #34 引入 0.17.0 后未改动），fork 未检查入口是否随包。
- **解决方案:** 全范围打包（core+training+legacy+rl+post_training+inference），
  顶层入口文件（`gpt_builders` / `mamba_builders` / `model_provider` /
  `pretrain_gpt` / `pretrain_bert` / `pretrain_mamba` / `pretrain_t5` /
  `pretrain_vlm` / `train_rl`）一并纳入 wheel（MLF PR #107
  feat/wheel-full-scope）。§2~§5 四场景验证均基于该 wheel。
- **注意事项:** `examples/` 目录不打进 wheel（测试环境文件，如
  `examples/rl/environments/countdown/`，需单独拷贝）；wheel 自带编译扩展
  `helpers_cpp*.so` 位于 site-packages，而 `compile_helpers()` 在**源码树**
  中查找——"repo checkout + 已安装 wheel"的混用形态需先把 `.so` 植入源码树，
  对 app 镜像无影响，单步安装即完整。
  打包范围的后续演进要检查入口文件是否仍随包。
- **现在状态:** 已关闭（PR #107）。PR 合入前其余后端暂不能复用该 wheel 做按序验证。

### 1.2 未声明运行时依赖（NVIDIA 上游代码缺口）

**METADATA 声明的依赖面 ≠ 真实运行时依赖面。**

- **现象:** 依赖被实际使用却未声明，import 期 try/except 吞错或直接崩。
- **实例（非 RL 场景）:** psutil——异步 checkpoint 的
  `FileSystemWriter` worker 线程实际调用 `_process_memory()`，却既不在 wheel
  METADATA 的 `Requires-Dist`（仅 `torch>=2.6.0` / `numpy` /
  `packaging>=24.2` + optional extras）也不在 runtime 镜像内；触发即抛
  `RuntimeError("psutil is not installed, ...")`。
- **解决方案:** 反馈本 fork 在 `pyproject.toml` 补声明（psutil → PR #106）；
  build-infra 侧在 runtime 依赖面兜底。
- **现在状态:** psutil 已提交（PR #106）。RL 场景的依赖缺口清单见 §5.1
  （tensorboard / wandb / httpx 等一组，待反馈）。

### 1.3 vendor 包问题（逐包归纳全部修改）

vendor 包（`flagos-pypi-{vendor}` 上我们掌控、可 repack）的问题分四类：
**元数据不可信、包间版本失配、平台覆盖不全、源码杂质**。四类问题逐包归纳，供其他平台照做；今后其他 vendor 包的修正在此追加。

#### 1.3.1 flash_attn 2.8.3+das.opt1.dtk2604.torch290

- **现象:** RL dynamic 引擎版本断言失败（要求 ≥2.7.3，见 §5.5）。
- **修改归纳（repack 共 4 处）:**
  1. `__init__.py` `__version__`：硬编码 `"2.6.1"` → `2.8.3`
  2. `version.py` `version` 字段：`2.6.1` → `2.8.3`（连同 git_hash /
     git_branch / abi / dtk / torch_version / hcu_version 等元数据校正）
  3. dist-info METADATA `Version`：→ `2.8.3+das.opt1.dtk2604.torch290`
  4. 源码中无意义的 `import pytest`（import 即报错）→ 移除
- **注意事项:** 版本值出现在 3 处（`__init__.py` / `version.py` /
  dist-info METADATA），repack 时**三处都要改并保持一致**——漏改任一处，
  `get_fa_version_str()`（源码 `__version__` 优先，importlib.metadata
  fallback）仍会读到不一致版本。版本校验以 wheel 实际为准，源码
  `__version__` 不可信。
- **现在状态:** 已修正（三处一致 = 2.8.3），§5.5 断言实证通过。

#### 1.3.2 transformer_engine 2.10.0+das.opt1.dtk2604.torch290

- **现象:** `import transformer_engine.pytorch` 报错（缺 pandas）；triton 量化模块调用报错（参数无法识别）。
- **修改归纳（repack 共 3 项）:**
  1. **pandas 补声明:** Requires-Dist 漏 pandas（现声明：torch==2.9.0、
     importlib-metadata>=1.0、einops、pydantic、packaging），而 triton 量化模块（
     `pytorch/triton/blockwise_int8_gemm_nt*.py`、`per_token_group_quant.py`）
     import pandas → 补 `pandas>=2.0,<3`，带版本约束防公共 index 漂移（窗口由
     runtime python 3.10 + numpy 1.26.4 限定）。
  2. **enable_mmacfuse 剥参:** TE 2.10.0 为 ROCm/HCU 适配加入的参数，传给
     triton `Config`——flagtree 3.6.0 与 vendor triton 3.5.1 的 Config 签名均不接受（厂商各包之间的版本失配）→ repack 时剥离。
  3. **FA 版本检测剥 local version:** TE 内部检测 flash_attn 版本时，版本串的
     local version（`+das.opt1.dtk2604.torch290`）干扰比较 → 检测时剥离。
- **验证:** repack 后从 hygon index 单步安装即完全可用（import +
  LayerNorm/Linear + DPA thd/fp16 FA 后端均通过）。
- **注意事项:** 安装侧修复后正常装 TE（带 aliyun extra index）即自动拉
  pandas，无需在 configs.yaml 单独治理。
- **现在状态:** 已闭环交付。RL 用 TE 方向已定（§5.4）。

#### 1.3.3 modelopt（平台覆盖不全）

- **现象:** post_training 场景依赖 modelopt（HARD 依赖）。
- **原因:** 仅 enflame 有 vendor 变体（`enflame-modelopt`）；NVIDIA 用
  NVIDIA modelopt 可用，其余后端成功率不确定。
- **处置:** 带依赖解析 ad-hoc 装入 runtime venv（aliyun 镜像；PuLP/
  antlr4-python3-runtime-4.9.3/nvidia-ml-py/omegaconf/scipy 随装，torch
  2.9.0 落位未动），**未入镜像**——与其余场景的"单步安装 wheel 即可用"
  不同，违反交付目标。
- **现在状态:** 纳入镜像与否待镜像层决策。

#### 1.3.4 triton 3.5.1+das.opt1.dtk2604.torch290（torch 依赖剥除）

- **现象:** 默认 `compiler flagtree` 环境抛 `No module named 'torch'`。
- **原因（torch 落位 bug）:** 3.5.1 原 wheel 声明 torch 依赖，
  `pip install --target /opt/triton` 把 torch 捎进 /opt/triton；随后 DEPS 装
  torch（带 `PYTHONPATH=/opt/triton`），pip 判定 torch 已满足 → site-packages
  无 torch → 默认 flagtree 环境 import 失败。
- **修改归纳（repack 1 项）:** 去掉 wheel 的 torch 依赖（torch 由此真正进
  site-packages，两编译器环境皆可用）。flash_attn 同款剥除 pytest 依赖
  （§1.3.1）。
- **注意事项:** 属"包间版本失配"类（§1.3 四类）；其余 vendor 平台 triton
  wheel 若声明 torch 依赖，同装法会踩同型坑——新平台先查 dist-info METADATA
  依赖列表。
- **现在状态:** 已修复（torch 落位 bug 关闭）。

### 1.4 平台移植性默认值（fused kernel / jit_fuser）

- **fused kernel 默认开启且依赖 CUDA-only 扩展:** `masked_softmax_fusion`
  默认开启（`--no-masked-softmax-fusion` 为 store_false 开关），而 fused
  softmax 路径 `get_batch_per_block()` 内 `import
  scaled_masked_softmax_cuda`（CUDA-only 编译扩展，DCU 上不存在）——非 CUDA
  平台必须显式传 `--no-masked-softmax-fusion`，否则 `ModuleNotFoundError`。
  megatron 默认假设其 fused kernel 一定可用；对非 CUDA 平台这些默认值需要逐一显式关闭——平台移植性的普遍缺口，非 hygon 独有。
- **jit_fuser 在模块 import 期绑定 `torch.compile`:** `enable_jit_fuser()`
  在**模块 import 时即执行**（`megatron/core/jit.py:16-33`），把全局
  `jit_fuser` 绑定为 `torch.compile`；`--disable-jit-fuser` 在 args 解析之后才翻转全局，**晚于装饰器生效点**，无法阻止训练 warmup 期的
  `torch.compile`。旧镜像（无 DTK LLVM 包，§1.5）warmup 期 flagtree 编译失败
  → HSACOError；DTK LLVM 包后两编译器皆可编译，flagtree 下是否仍需
  `--disable-jit-fuser` 待复测（RL 复测被 tensorboard 阻塞，未到达 warmup，
  §5.1）。修复方向：`jit_fuser` 改为惰性装饰（或
  `enable_jit_fuser` 默认 no-op，由训练入口显式开启）。
- **现在状态:** 待反馈本 fork。

### 1.5 工具链：编译器可用性与 DTK LLVM 前置（flagtree"屏蔽"已修正）

- **现象（早期结论，已修正）:** flagtree 3.6.0 曾判"无法编译 HCU kernel"——
  `make_amdgcn()` 调 clang 子进程，HCU 的 `-mllvm` flags 被拒 → clang
  静默退出、无产物 → 误导性 `HSACOError("File operation failed: ...")`。
- **原因（误判根因）:** 失败来自**旧容器**——base 镜像未装 DTK LLVM 包。
  PR #403 在 hygon base 镜像加入 DTK LLVM（`dtk_llvm.run`，`base/hygon-dtk26.04`
  内 `bash /llvm.run --dtk_dir /opt/dtk-26.04`），提供 clang-18 于
  `/opt/dtk-26.04/aillvm/bin/clang-18`——这是两编译器自动可用的前置。
- **机制:** flagtree 3.6.0（`triton/backends/hcu/compiler_hcu.py`）与 vendor
  triton 3.5.1（`triton/backends/amd/compiler_hcu.py`）有**同一段 dtk 特判**：
  `llvm_subdir = "aillvm" if rocm_path.name == "dtk" else "llvm"`。`/opt/dtk`
  是符号链接（→ /opt/dtk-26.04），`Path.name` 恰为 "dtk" → 走 aillvm 分支 →
  自动找到 clang-18，无需 env / export。**同源同机制。**
- **当前状态（2026-08-16 实测修正）:** 两编译器均可编译 HCU kernel。flagtree
  下 flag_gems.mm / addmm / mm-bf16 全过（max_abs_diff=0.0）；早前手写 kernel
  的 52.96 差异是 kernel 自身 bug，非编译器问题。
- **注意事项:**
  - vendor triton 3.3.0 → 3.5.1（PR #404 升级）；"`llvm.translate_to_asm()`
    直出码、无 clang 子进程"是 3.3.0 的机制，3.5.1 调**外部 clang 子进程**——
    编译器机制结论不跨版本移植。
  - flagtree 唯一曾真实阻塞 = torch 落位 bug（§1.3.4）：triton 3.5.1 wheel
    声明 torch 依赖，捎带致 site-packages 无 torch → 默认 `compiler flagtree`
    下 `No module named 'torch'`。已由 repack 去掉 torch 依赖修复。
  - 验证面规则：每个后端 × 每个编译器都要验证；编译器结论不跨平台移植。
    镜像内置 `compiler` 函数（来自 BASH_ENV）切换编译器。
- **现在状态:** 两编译器皆可用（DTK LLVM 包 + triton repack 后）；"默认改
  vendor triton / 移除 flagtree"不再需要。

### 1.6 环境：DTK 已内置，无需 source env.sh

- runtime 镜像已内置 DTK 环境：经 bash 运行的命令（含非交互）可直接
  `import torch`（实测：容器内非登录 `bash -c '/flagos/bin/python -c "import
  torch"'` 直接成功，torch 2.9.0）。
- **注意事项:** 直接 `docker exec <容器> /flagos/bin/python ...` 即可；**不要额外加 `source /opt/dtk-26.04/env.sh`**。

## 2. training

**结论:** 全范围 wheel 单步安装直跑 `pretrain_gpt.py`，exit 0（无需 repo
checkout；`megatron.training` 已在 wheel 中，§1.1）。**3.5.1 复验通过
（2026-08-17）**：`compiler triton` 下 mock data 5 iter 全跑完 exit 0
（loss 1.084036E+01 → 1.083188E+01，lr 1e-6 constant 下降极小符合预期；
3.3.0 时代 loss 9.1295→8.8622 因当时参数/初始化不同不直接可比），参数 =
本节省 DCU 基线（--no-masked-softmax-fusion --disable-jit-fuser
--no-persist-layer-norm --no-gradient-accumulation-fusion
--attention-backend unfused --transformer-impl local --bf16）+
--untie-embeddings-and-output-weights + seed 42。

**可复现运行参数基线**（DCU 上完整跑通 megatron 训练的最小 flags / 容器配置；rl 场景引用，并在 §5 中给出 RL 特有参数）：

| 参数 / 配置 | 原因 |
|---|---|
| `--no-masked-softmax-fusion` | §1.4：fused 路径 import CUDA-only 扩展 |
| `--disable-jit-fuser` | vendor triton 下不需要；flagtree 下旧结论（无法编译 HCU）已证伪，是否仍需待复测（§1.4 + §1.5） |
| `--no-persist-layer-norm` / `--no-gradient-accumulation-fusion` | 相应 fused kernel 在 DCU 上不可用的显式关闭 |
| `--attention-backend unfused` | 仅 local 训练线需要；RL（TE）线不传（§5.4） |
| `--transformer-impl` | 训练用 `local`；RL 必须 `transformer_engine`（§5.4） |
| `--shm-size=8g`（docker run） | torch multiprocessing 需大于容器默认 64MB 共享内存 |

### 2.1 venv 缺 python3-config（2026-08-16 实测）

- **现象:** venv `/flagos/bin` 缺 `python3-config` 符号链接。
  `compile_helpers()`（`megatron/core/datasets/utils.py`，带 FlagScale 来源标注的
  fork 补丁）执行 `subprocess.check_output(["python3-config",
  "--extension-suffix"])` 抛 `FileNotFoundError: 'python3-config'`，
  `pretrain_gpt.py` 在数据集构建 import 期即挂。该函数只在 wheel 已带预构建
  `helpers_cpp{ext_suffix}.so` 时提前 return 跳过 make——但仍需
  python3-config 算后缀。
- **原因:** uv 托管的 Python 自带该二进制（不在 venv 路径），venv 未链接。
- **解决方案:** `compile_helpers()` 改用 `sysconfig.get_config_var("EXT_SUFFIX")`
  （标准库，任何 Python 环境都有），替代 `subprocess.check_output([...])`。
  两路落地、最终落成同一段代码形态，不依赖 MLF merge 节奏：
  - **MLF 侧（PR 已提交）:** PR #112（与 psutil PR #106 同类的上游修复）。
  - **build-infra 侧（已落地）:** wheel 是 build-infra 自产，沿用现有
    on-the-fly patch + grep gate 模式新增
    `packaging/megatron/builder/patch-compile-helpers-sysconfig.py`，在 wheel
    构建时对 checkout 打同样的 sysconfig 补丁。脚本幂等且自 gate：已是
    sysconfig 形式 → no-op（PR #112 合并后自动跳过）；仍是 python3-config
    形式 → 就地替换；源码演进（两种形式都找不到）→ exit 1 硬失败，补丁不可能静默失效。
- **现在状态:** 已落地（build-infra 兜底）；PR #112 待合并。

## 3. post_training

**结论:** driver 跑通（post_training surface 全 import + `simple_generate`，
输出 shape=(1, 8)，exit 0）。**3.5.1 复验通过（2026-08-17）**：`compiler
triton` 下同一 driver exit 0，输出 shape=(1, 8)，与 3.3.0 时代事实一致；
checkpointing.py:7 模块级 `import modelopt.torch` 由 ad-hoc 装入的
nvidia-modelopt 0.45.0 满足。

- **前提:** nvidia-modelopt 0.45.0 带依赖解析 ad-hoc 装入 runtime venv
  （aliyun 镜像：PuLP/antlr4-python3-runtime-4.9.3/nvidia-ml-py/omegaconf/
  scipy 随装，torch 2.9.0 落位未动），**未入镜像**——与其余场景的"单步安装
  wheel 即可用"不同，违反交付目标（§1.3.3）。
- **注意:** modelopt 是唯一有 vendor 变体的 HARD 依赖；其余后端成功率不确定（§1.3.3）。

## 4. inference

**结论:** `StaticInferenceEngine(controller, legacy=True)`，3 请求 × 8 tokens
（`prompt_tokens` 直接注入 `InferenceRequest`，绕过 NullTokenizer 无
`tokenize()` 的限制），generate 4.2s，exit 0。**3.5.1 复验通过（2026-08-17）**：
同构 driver 生成 4s（tqdm 3/3 [00:04, 1.49s/it]），与 3.3.0 时代 4.2s 吻合；
NullTokenizer 无 detokenize，复验 driver 补最小实现（controller.detokenize
无条件 `inspect.signature`，text_generation_controller.py:209）。

- **正面经验:** legacy 静态引擎路径保留 `StaticInferenceContext` →
  `is_static_batching()=True` → attention.py static 分支
  `apply_module(core_attention)`（DotProductAttention/sdpa）——**不依赖
  flash-attn、不编译 triton kernel**，对 hygon 属编译器无关路径。
- **注意:** 非 legacy 路径内部构造 DynamicInferenceContext +
  DynamicInferenceEngine → 回到 §5.5 的 flash-attn 依赖。

## 5. rl

**结论:** 全链路首次跑通（exit 0）：tokenizer → NCCL 初始化 → TE 模型构建 →
dynamic 引擎（cuda graph 构建）→ text-gen server → "Collecting rollouts,
Iteration 0..." → PAD/EOD 日志 → `compute_logprobs_batch` TE forward → 2 个训练迭代 →
`[exiting program at iteration 2]`，0 Traceback，"Inference
Coordinator: shut down successfully"。rl 四步（rollout → logprob → 训练 →
退出）首次在 hygon25 全通。
**前提:** 补装 §5.1 未声明依赖（测试用途，aliyun）+ §5.4 vendor TE。
**配方相应改动:** `--transformer-impl local → transformer_engine`、删
`--attention-backend unfused`（local 时代 DCU 基线）。

**RL 特有可复现参数**（参数组合类教训，实测验证）:

| 参数 / 配置 | 原因 |
|---|---|
| `--inference-max-seq-length` ≥ prompt 长度 + 期望生成长度 | 小于 prompt 长度时 `tokens_to_generate` 为负，dynamic 引擎拒绝全部请求 |
| `--inference-dynamic-batching-max-tokens` 高于 max_requests | 覆盖引擎默认上限，否则 max_tokens ≥ max_requests 断言失败 |
| `--transformer-impl transformer_engine` | §5.4：RL 训练 forward 强制 TE，local 走不通 |
| tokenizer 数据层补 eos | §5.3：无 eos 时 `prepare_trajectories` 抛 TypeError |

### 5.1 未声明依赖（主要耗时项）

**tensorboard 实例:** `megatron/rl/rl_utils.py:24` 模块级
`from torch.utils.tensorboard import SummaryWriter` → 运行时需要 tensorboard
包；runtime 镜像与全作用域 wheel 的 METADATA 均未声明 → `training.py:60-67`
的 `has_rl_utils` try/except 捕获 ImportError 置 False → `training.py:2744`
断言 `RL cannot run without the megatron.rl package`（rc=1）。

**依赖面缺口清单**（import 链逐层探测，对照 pyproject 声明）:
`megatron/rl` 的模块级第三方依赖与 pyproject 声明有系统性偏差——不止
tensorboard 一个，而是一组，偏离方式分三种：

| 依赖 | 使用位置（模块级 import） | pyproject 声明 | 偏离方式 |
|---|---|---|---|
| tensorboard | `rl_utils.py:24` `torch.utils.tensorboard` | **未声明** | 完全未声明 |
| wandb | `rl_utils.py:92` `from wandb import wandb_run` | 仅 `training` extra（`mlm` 是其废弃副本） | 声明在 training extra，`rl` extra 没带 |
| httpx | `inference/megatron.py:6` | **未声明** | 完全未声明 |
| tqdm | `agent/reward_only_agent.py:7` `tqdm.asyncio` | `dev`/`lts` extra | 声明在 dev/lts extra，`rl` extra 没带 |
| openai[aiohttp] | `inference/megatron.py:8` | `dev` extra | 声明在 dev extra，`rl` extra 没带 |
| uvicorn | `server/agent/fastapi_env_server.py:12`、`server/inference/inference_interface_server.py:12` | **未声明** | 完全未声明 |
| fastapi | `server/agent/fastapi_env_server.py:9` 等 | `dev` extra | 声明在 dev extra，`rl` extra 没带 |
| datasets | `agent/huggingface_dataset_agent.py:3` | `dev` extra | 声明在 dev extra，`rl` extra 没带 |
| transformers | `tokenizer/huggingface_tokenizer.py`（`AutoTokenizer`） | 仅 `training` extra | 声明在 training extra，`rl` extra 没带 |
| pyzmq | `core/inference/engines/dynamic_engine.py:76-80`（`import zmq` → `HAVE_ZMQ`） | **未声明** | 完全未声明 |
| msgpack | `core/inference/engines/dynamic_engine.py:481`（`assert HAVE_MSGPACK`） | **未声明** | 完全未声明 |
| quart | `core/inference/engines/text_generation_server.py:58`（Quart 不可用） | `dev` extra | 声明在 dev extra，`rl` extra 没带 |
| hypercorn | text_generation_server 同路径（Quart 的 ASGI server） | `dev` extra | 声明在 dev extra，`rl` extra 没带 |

（numpy / yaml / typing_extensions 为运行时基础，runtime 镜像已含，不属缺口。）

**关键点:**

- **wandb 比 tensorboard 更隐蔽:** tensorboard 是"完全没声明"，wandb 是
  "声明了但挂在 `training` extra 上"——`rl` extra（`pydantic==2.12.5` +
  `tensorboard==2.19.0`，MLF 分支 `feat/rl-optdeps-verify` 3824c85b8）与
  `training` extra 互不包含，装 `[rl]` 仍缺 wandb。
- **性质:** 与 §1.2 psutil 同类——NVIDIA 上游代码的未声明运行时依赖，本
  fork 继承。修复方向 = 反馈本 fork 把 RL 实际用到的依赖收进 `rl` extra
  （wandb/tqdm/openai[aiohttp]/httpx/uvicorn/fastapi/datasets），或
  build-infra 侧在 runtime configs.yaml 依赖面兜底。
- **版本基准（2026-08-16 定）:** 容器内手补包只允许测试用途；版本以 MLF pin
  为准（tensorboard 2.19.0 / pydantic 2.12.5），已把容器实测版（2.21.0 /
  2.13.4）降回。公共包安装一律走 aliyun 镜像（pypi.org 慢）。
- **现在状态:** 待反馈本 fork（RL 依赖 extra 声明偏差）。

### 5.2 datasets / pyarrow 版本兼容缺陷（2026-08-17 实测）

- **现象:** datasets 5.0.1 `save_to_disk` 产物无法被
  `load_dataset("arrow")` 重读——
  IPC stream 尾部带零长消息终止符（`ff ff ff ff 00 00 00 00`），
  pyarrow ≤25 的 stream 迭代误读为 538970747
  字节长度前缀（`ArrowInvalid: Expected to read 538970747 metadata bytes` →
  回退 `Not an Arrow file`）。
- **非数据损坏:** 小文件同复现；`pa.ipc.new_file`（ARROW1 footer）与
  `pa.ipc.new_stream`（纯流）两种手工写法均验证可被 load_dataset 读取；
  pyarrow 降级亦不修（同版本写+读也挂）。
- **解决方案:** 容器内以 `pa.ipc.new_stream` 手工重写数据集（全量
  490364 行），round-trip 验证通过。
- **对 CI 的意义:** MLF grpo 测试的预生成 artifact 若用同一
  (datasets 5.0.1, pyarrow ≤25) 组合生成会踩同坑——CI 需固定经过实测的
  (datasets, pyarrow) 版本对。
- **现在状态:** 已规避；CI 版本对待定。

### 5.3 tokenizer 无 eos

- **现象:** gpt2 tokenizer 无 eos token → 包装器 `eod` property 返回 None →
  `prepare_trajectories`（`rl_utils.py:1085`）在日志行
  `detokenize([tokenizer.eod])` 处 TypeError（`int() argument ... not
  'NoneType'`）。
- **解决方案（数据层修复即可，无需改 megatron core）:**
  `tokenizer_config.json` 声明 `bos/eos/unk = "<|endoftext|>"`，包装器
  `add_special_tokens` 的 copy-back 循环（`huggingface_tokenizer.py:208-209`）
  把底层 HF tokenizer 的 eos 传播到包装器 → `eod` = 50256
  （`<|endoftext|>`）。实测：tokenizer 检查输出 `eod: 50256`；运行日志
  `Tokenizer EOD: '<|endoftext|> (50256)'`。qwen3 系 tokenizer 天然带 eos，
  不需此处理。
- **附带发现:** `eos_id`（`huggingface_tokenizer.py:310-312`）缺 None 守卫。
- **现在状态:** 已解决。

### 5.4 RL 训练 forward 必须 TE（local 不支持 THD 打包序列）

- **现象:** `get_logprobs`（`rl_utils.py:666-679`）**无条件**构造打包序列（THD）格式的 `packed_seq_params`（即使 `sequence_packing=False`，为 CUDA
  graph 签名一致性）→ 传给模型 → local `DotProductAttention` 断言 "Packed
  sequence is not supported by DotProductAttention. Please use
  TEDotProductAttention instead."（`dot_product_attention.py:158-161`）。
- **原因:** RL 训练 forward 需要 `--transformer-impl transformer_engine`
  （`te` 为非法值；CI qwen3 grpo 从不传 `--transformer-impl`，默认 TE → CI
  从未覆盖 local 的 RL 训练 forward）。DCU 有 vendor TE
  `2.10.0+das.opt1.dtk2604.torch290`（§1.3.2）。
- **平台依赖警告:** 并不是所有后端都有厂商提供的 TE——无 vendor TE 的平台要么等 MLF 支持 local 的 THD 打包序列训练 forward，要么平台侧自行构建/
  适配 TE。
- **现在状态:** hygon 已跑通（vendor TE repack 后单步安装即用，§1.3.2）；
  无 vendor TE 平台待反馈。

### 5.5 flash_attn：RL dynamic 引擎硬依赖 ≥2.7.3

- **现象:** RL 场景的动态推理引擎（`megatron/rl/inference/megatron.py:87`
  硬编码 `get_dynamic_inference_engine` → dynamic 引擎
  `attention.py:943` `assert HAVE_FA3 or is_fa_min_version("2.7.3")`）硬依赖
  flash-attn ≥ 2.7.3（无 FA3 时）。
- **根因与修复:** vendor flash_attn wheel 版本字符串三处不一致，致
  `is_fa_min_version("2.7.3")` 误判为 False——
  repack 修正三处字符串一致后断言通过（完整修改归纳见 §1.3.1）。
- **实证:** 修复后 `flash_attn.__version__` = `"2.8.3"` →
  `is_fa_min_version("2.7.3")` 通过（无需 FA3），dynamic 引擎断言实证通过。
- **现在状态:** 不再是阻塞（hygon 已由 vendor flash_attn 2.8.3 满足）；无
  vendor flash_attn 的平台需先做同样检查。

## 6. 跟踪事项

**已提交至本 fork（flagos-ai/Megatron-LM-FL）:**
- PR [#105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105)——
  §1.1 `megatron.training` import 修复
- PR [#106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106)——§1.2
  psutil 依赖声明
- PR [#107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107)——§1.1
  全范围打包
- PR [#112](https://github.com/flagos-ai/Megatron-LM-FL/pull/112)——§2.1
  python3-config → sysconfig

**待反馈至本 fork:**
- §1.4 jit_fuser import 期绑定时序、fused kernel 默认开启的平台假设
- §5.1 RL 依赖 extra 声明偏差（tensorboard/wandb/httpx/tqdm/openai/uvicorn/
  fastapi/datasets/transformers/pyzmq/msgpack/quart/hypercorn 实际使用与
  `rl` extra 不符）
- §5.4 local impl 不支持 THD 打包序列训练 forward（RL 训练 forward 被迫依赖
  TE）；无 vendor TE 平台的适配路径

**待决策:**
- §1.3.3 modelopt 纳入镜像与否
- §5.2 (datasets, pyarrow) 实测版本对固化到 CI
- §1.4 flagtree 下是否仍需 `--disable-jit-fuser`（RL E2E 复测确认；复测被
  §5.1 tensorboard 阻塞，未到达 warmup）

**相关文档:** `packaging/megatron/builder/report-megatron-0.17.1.md`（构建与依赖面；
依赖处理并入其 §1/§3）。
