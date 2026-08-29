---
name: hygon-compiler-mask
description: hygon DTK 26.04 编译器可用性 mask 表——flagtree 屏蔽、vendor triton 交付；验证面不归并规则
metadata:
  type: project
---

# 编译器 mask 表（hygon DTK 26.04，2026-08-13 实测；flagtree 结论 2026-08-16 修正）

## mask 表

| 编译器 | 版本 | HCU kernel 编译 | 结论 |
|---|---|---|---|
| flagtree | 3.6.0 | ⚠️ 旧容器 clang-17 失败 → **2026-08-16 新镜像实测通过**（见 §3.5.1 机制） | **可用**（修正"屏蔽"结论） |
| vendor triton | 3.3.0 | ✓ `make_amdgcn()` 用 `llvm.translate_to_asm()` 直接出码，无 clang 子进程 → 正常产出 `.amdgcn` | **交付**（已被 3.5.1 取代） |

## 归并规则（用户定案）

- **验证面不归并**：每个后端 × 两个编译器（flagtree/triton）都要验证。如果有一个编译器不能用，只能屏蔽它。
- **交付面归并**：每后端只交付能用的编译器；不能用的屏蔽（不设为默认 / 不装）。编译器不翻倍镜像数。
- 后端版本（如 metax 3.7.2.x / 3.8.1.x）是真矩阵，每后端一张 runtime + 一张 app 镜像。

## 关键机制

- 运行时镜像**同时带** flagtree 和 triton 两套，`compiler` 函数（BASH_ENV 内置）切换：`compiler triton`。
- 无 `compiler` 函数时手动切换：
  `export PYTHONPATH="/opt/triton:$(printf %s "${PYTHONPATH}" | tr ':' '\n' | grep -v '^/opt/flagtree' | paste -sd: -)"`
- **现状缺口**：hygon DTK 26.04 runtime 镜像的**默认编译器是 flagtree**，但 torch 落位 bug（torch 只在 /opt/triton）让 `compiler flagtree` 环境 import torch 失败——**修复 = repack triton 3.5.1 wheel 去掉 torch 依赖**（用户定案），两编译器环境即都可用。属 runtime/repack 交付工作。不再需要"默认改 vendor triton / 移除 flagtree"。

## 对 megatron 参数的影响

- flagtree 下的旧结论：需要 `--disable-jit-fuser` 规避 §1.3 import 期绑定 + 无法编译 HCU。**"无法编译 HCU"已证伪**（2026-08-16 flag_gems 全过）；`--disable-jit-fuser` 是否仍需，待新镜像 flagtree 环境 E2E 复测确认（RL(GRPO) 场景下一步）。
  - **2026-08-16 RL 复测进度：** rl-new 容器（repack 修复后新镜像）已启动 RL(GRPO) E2E（flagtree 默认，刻意不传 `--disable-jit-fuser`），但**先被 tensorboard 未声明依赖在 import 期阻塞**（`megatron/rl/rl_utils.py:24` → `has_rl_utils=False` → 断言，详见 [[megatron-0.17.1/backends/hygon25.md]] §5.4），尚未到达 jit-fuser warmup 阶段 → **mask-doc 问题仍未回答**。tensorboard 补上后，下一预期阻塞是 flash-attn `__version__` 硬编码 "2.6.1"（§5.1 修正）。
- vendor triton 下**不需要**——`--disable-jit-fuser`、jit.py 补丁都去掉，E2E 复跑 exit 0（loss 9.1295→8.8622）。

详见 [[megatron-verification-state]]。

## 追加：triton 3.5.1（clang-18 修正版结论，2026-08-16 实测）

| 编译器 | 版本 | HCU kernel 编译 | 结论 |
|---|---|---|---|
| vendor triton | 3.5.1 (`+das.opt1.dtk2604.torch290`) | ✓ **DTK LLVM 包 clang-18**（PR #403，`/opt/dtk-26.04/aillvm/bin/clang-18`）下 p8 + mmac 全过 | 3.5.1 **可以工作**，修正早前"否决"结论 |
| flagtree | 3.6.0 | ✓ 同款 aillvm/clang-18 机制（`compiler_hcu.py` 里**同一段 dtk 特判**），**2026-08-16 实测 flag_gems.mm / addmm / mm-bf16 全 OK**（max_abs_diff=0.0） | **可用**（修正"屏蔽"） |

### 2026-08-16 flagtree 修正（为什么之前判"屏蔽"错了）

- flagtree 3.6.0 的 `triton/backends/hcu/compiler_hcu.py` **与 triton 3.5.1 有同一段 dtk 特判**：`llvm_subdir = "aillvm" if rocm_path.name == "dtk" else "llvm"`（275-278 行），`path_to_rocm_clang()` 默认 `llvm_path/bin/clang-18` → `/opt/dtk/aillvm/bin/clang-18`（302-319 行）。
- 早前"clang-17 子进程被拒"结论来自**旧容器**（无 DTK LLVM 包）；PR #403 的 dtk_llvm.run 之后 flagtree 与 triton 3.5.1 **同源同机制**，都自动找到 clang-18。
- **实测**（容器 rl-3.5.1，`PYTHONPATH=/opt/flagtree:/opt/triton`，bash -lc）：`flag_gems.mm` fp32 OK(0.0)、`addmm` OK(0.0)、`mm` bf16 OK(0.0)。flag_gems 5.3.4。
- 早前手写 mm kernel（/tmp/mm_test.py）max_abs_diff=52.96 **是 kernel 自身 bug**（k-loop 指针更新/mask 写法），不是编译器问题——用 flag_gems 规范 op 复测即全 0。
- **flagtree 唯一真实障碍 = torch 落位 bug**（见下）：`compiler flagtree`（默认）时 `No module named 'torch'`，是 triton repack 的镜像层问题，不是 flagtree 编译问题。

### 3.5.1 机制（clang-18 修正）

- 3.5.1 hcu 后端在 `triton/backends/amd/compiler_hcu.py`，`make_amdgcn()` 调**外部 clang 子进程**；`path_to_rocm_llvm()` 里 **dtk 特判**：`llvm_subdir = "aillvm" if rocm_path.name == "dtk" else "llvm"`。
  - 但 **ROCM_PATH=/opt/dtk** 是符号链接（→ /opt/dtk-26.04），`Path.name` = "dtk" → 走 aillvm 分支 → **自动找到 clang-18**（无需手动 export，clang-17 回退只在 aillvm 缺失时发生）。
  - 早前 HSACOError 是**旧容器**（无 dtk_llvm.run / 手动 export 覆盖）的产物；新镜像（含 #403）**无 env、无 export，直接 RESULT_OK**。
- **torch 落位 bug（新发现，镜像层问题）**：`pip install --target /opt/triton triton-3.5.1...torch290` 把 torch 捎进 /opt/triton；之后 DEPS 装 `torch==2.9.0+das.opt1.dtk2604` 带 `PYTHONPATH=/opt/triton`，pip 判定 torch 已满足 → **site-packages 无 torch**。后果：
  - `compiler triton`：torch ✅（借 /opt/triton/torch）+ triton 3.5.1 ✅ + add kernel **RESULT_OK True**。
  - `compiler flagtree`（默认）：`No module named 'torch'` ❌。
  - **修复方向（用户定案）**：repack triton 3.5.1 wheel，**去掉 torch 依赖**（triton 声明了 torch 依赖才被捎带）；DEPS 的 torch 由此真正进 site-packages，两编译器环境皆可用。属 runtime/repack 交付工作。
- configs.yaml hygon.dtk26.04 现在写的是 `triton==3.5.1+das.opt1.dtk2604.torch290`（PR #404 升级，3.3.0 已弃用）；`flagtree==0.6.1+hcu3.6` 仍在配置里。

### vendor 包问题（2026-08-16，已修复）

- **flash_attn**（`flash_attn==2.8.3+das.opt1.dtk2604.torch290`）厂商 wheel 的依赖声明里**带了不该有的 pytest**（未声明的 pytest 依赖）→ pip 装 flash_attn 时把 pytest 一并装进 site-packages（实测 `/flagos/lib/python3.10/site-packages/pytest-9.1.1.dist-info` 存在，DEPS 未显式列 pytest）。**已通过重新打包（repack 剥离 pytest 依赖）修复**。
- 与 triton repack 同属一个交付动作：vendor 包问题统一靠 repack 修，不靠镜像内补丁。
