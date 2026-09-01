# WORKING-CONTEXT — sglang 0.5.18 插件分支 + 双后端验证 + 镜像制作

> 时效文件（agent-protocol §1/§5）：创建 → 使用 → 逐项并入
> `status_matrix.sglang0.5.18.yaml` + `docs/sglang-0.5.18/` per-version docs 后**删除**。
> 删除前检查 `git ls-files` 是否入库。本文件不重复已入库的 playbook/decisions 内容。

## 目标（用户 2026-09-01 定案）

在 sglang-plugin-FL 开 `exp/0.5.18` 主分支，落地 0.5.18 全部插件代码层面修补，
rebase 跟踪 main 前进；在分支上做全面后端验证与镜像制作。

## 用户交代的硬约束（原话要点）

1. **先建进度跟踪机制**（matrix yaml、PR 列表），再开始验证工作。
2. **验证范围**：先 metax-maca3.8.1.3 + ascend-cann9.0.0 两个后端，全部打通后
   再看"另外两个"（= metax-maca3.7.2.1 + ascend-cann8.5.0，届时与用户确认）。
3. **每后端分支**建在 exp/0.5.18 之上（如 exp/0.5.18/metax），承载 per-vendor
   FlagGems 算子屏蔽（落点 = **插件层 per-vendor 屏蔽表**，用户已确认），
   E2E 通过后 PR 合并回 exp/0.5.18。
4. **exp/0.5.18 是"主"分支**；rebase 跟踪 main。
5. **编排**：主会话（我）= 负责人，派 subagent 实操；subagent 遵守
   `docs/agent-protocol.md`（只出报告 + 授权代码改动，永不写 docs/memory/
   WORKING-CONTEXT）；进度由主会话监控；决策不清问用户。
6. 职责划分：插件代码修补（含屏蔽表）→ exp/0.5.18 分支体系；sglang wheel
   构建期 patch（setup_maca.py / clamp_position / vision.py）留在 build-infra
   `packaging/sglang/` 现有机制，不入分支。

## 分支体系（Phase 1，仓库 /Users/baai/work/sglang-plugin-FL）

- `exp/0.5.18`：从 origin/main（4aed74a）建，push -u（wheel 管线靠 plugin_ref
  消费，必须推送）。
- 两个基础修补 commit（通用 bug，后续单独 PR 回 main）：
  - `sglang_fl/platform.py:318` `is_pin_memory_available(self)` →
    `(self, device=None)`（对齐 0.5.18 SRTPlatform 接口；plugin main 未含，
    当前签名来自 thead PR #64）。
  - `pyproject.toml` 静态 version → setuptools-scm（wheel 版本带 `g<sha>`，
    app Containerfile 才能钉确切 commit）。
- 每后端分支：`exp/0.5.18/metax`、`exp/0.5.18/ascend`（插件已有
  `sglang_fl/dispatch/backends/vendor/<vendor>/` 结构，扩展 vendor dispatch）。
- main 前进时 `git rebase origin/main`；rebase 后版本 sha 变化属预期
  （旧 wheel 留 index，app 钉旧版本仍可装）。

## 阶段进度

- [x] Phase 0 进度跟踪机制：render_status_matrix.py 注册 sglang、
      `packaging/sglang/status_matrix.sglang0.5.18.yaml`、
      `docs/sglang-verification-matrix.md`（两 marker block）。
      已入库：**PR #670 已合并（a6476c2）**；verify 脚本随 PR 一并入库。
- [ ] Phase 1 exp/0.5.18 分支体系（基础修补 + per-backend 分支）。
- [ ] Phase 2 metax-maca3.8.1.3 验证（F/T 双路径；verify-sglang-backend.sh；
      新 wheel 重装重验，旧记录 sglang_fl-0.1.0 不背书）。
- [ ] Phase 3 ascend-cann9.0.0 全新验证（aarch64 cp311；llguidance 等 40 项
      依赖 aarch64 可得性是第一大 gate；shim vs 原生 sgl_kernel_npu 决策点）。
- [ ] Phase 4 sglang-plugin wheel 发布管线（镜像 vllm-plugin-wheel.yml；
      audit-deps 禁入 sglang；shim 上 per-vendor PyPI）。
- [ ] Phase 5 app/sglang/ Containerfile + workflow（镜像 app/vllm；metax +
      ascend 两个）。
- [ ] Phase 6 另两个后端（挂起）。

## 验证判据（metax / ascend 通用，F/T 双路径全过才算完成）

- 单步安装：`pip install sglang==0.5.18+flagos` + 插件 wheel。
- BEFORE/AFTER 依赖矩阵不变（torch/triton/flag_gems/numpy）。
- serve：Qwen3-0.6B，`--mem-fraction-static 0.6 --trust-remote-code
  --disable-cuda-graph --disable-piecewise-cuda-graph`，3× chat/completions：
  HTTP 200 + completion_tokens=144 + sampling_backend=pytorch。
- 开关：`SGLANG_IS_FLASHINFER_AVAILABLE=false`、`TORCHINDUCTOR_COMPILE_THREADS=1`、
  `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`、F/T 切换前移 flag_gems ConfigCache db。

## 编排纪律（防 context 膨胀）

- subagent 紧 brief：给精确文件路径与命令，明确"不要读无关文件"（用户明示）。
- 验证 subagent 按后端**串行**（设备竞争）；F/T 两路径在同一容器内顺序跑。
- 记录/入库由主会话执行；subagent 只报结果。
