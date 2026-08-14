---
name: hygon-compiler-mask
description: hygon DTK 26.04 编译器可用性 mask 表——flagtree 屏蔽、vendor triton 交付；验证面不归并规则
metadata:
  type: project
---

# 编译器 mask 表（hygon DTK 26.04，2026-08-13 实测）

## mask 表

| 编译器 | 版本 | HCU kernel 编译 | 结论 |
|---|---|---|---|
| flagtree | 3.6.0 | ✗ `make_amdgcn()` 调 clang-17 子进程，7 个 HCU `-mllvm` flags 中 5 个被拒 → clang 静默退出 0 但无产物 → 误导性 `HSACOError("File operation failed: ...")` | **屏蔽** |
| vendor triton | 3.3.0 | ✓ `make_amdgcn()` 用 `llvm.translate_to_asm()` 直接出码，无 clang 子进程 → 正常产出 `.amdgcn` | **交付** |

## 归并规则（用户定案）

- **验证面不归并**：每个后端 × 两个编译器（flagtree/triton）都要验证。如果有一个编译器不能用，只能屏蔽它。
- **交付面归并**：每后端只交付能用的编译器；不能用的屏蔽（不设为默认 / 不装）。编译器不翻倍镜像数。
- 后端版本（如 metax 3.7.2.x / 3.8.1.x）是真矩阵，每后端一张 runtime + 一张 app 镜像。

## 关键机制

- 运行时镜像**同时带** flagtree 和 triton 两套，`compiler` 函数（BASH_ENV 内置）切换：`compiler triton`。
- 无 `compiler` 函数时手动切换：
  `export PYTHONPATH="/opt/triton:$(printf %s "${PYTHONPATH}" | tr ':' '\n' | grep -v '^/opt/flagtree' | paste -sd: -)"`
- **现状缺口**：hygon DTK 26.04 runtime 镜像的**默认编译器是 flagtree（坏的）**——需在 runtime 镜像层修正（默认改 vendor triton 或移除 flagtree）。属 runtime 仓库工作。

## 对 megatron 参数的影响

- flagtree 下需要 `--disable-jit-fuser`（或 jit 旁路）规避 §1.3 import 期绑定 + 无法编译 HCU；
- vendor triton 下**不需要**——`--disable-jit-fuser`、jit.py 补丁都去掉，E2E 复跑 exit 0（loss 9.1295→8.8622）。

详见 [[megatron-verification-state]]。
