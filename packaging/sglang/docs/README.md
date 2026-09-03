# sglang 0.5.18 打包

入口文档。

| 文档 | 内容 |
|---|---|
| [zero-sgl-kernel-feasibility-20260828.md](zero-sgl-kernel-feasibility-20260828.md) | 零 sgl-kernel 可行性定案：flagos 默认路径已零依赖（6 op 全走 flag_gems），迁移面=vendor backend 约 2/3 op 有覆盖，缺口 enflame 2 op + kunlunxin klx_* |
| [zero-sgl-kernel-arch-20260828.html](zero-sgl-kernel-arch-20260828.html) | 零 sgl-kernel 方案架构图（本地 HTML，仅参考）|
| [sglang-0.5.18/backends/metax-0.5.12.md](sglang-0.5.18/backends/metax-0.5.12.md) | 0.5.12 零 sgl-kernel 参考记录（0.5.18 方案的前身实证：flag_gems ConfigCache 跨编译器污染根因链）|
| [sglang-0.5.18/](sglang-0.5.18/) | **0.5.18 per-vendor wheel + app 镜像验证报告**（index / playbook / decisions / backends / verification-matrix）|

## 结论速览

- **打包模型（2026-08-28 定案）**：统一 runtime + 单步安装（per-vendor wheel）。
  每个后端在自己的 runtime `-build` 镜像内从同一 sdist
  （`sglang-0.5.18.tar.gz`）构建 wheel；srt_empty 非 CUDA variant 基座天然
  零 torch 零 sgl-kernel，repack 仅打 `+flagos` 后缀；硬件算子收敛到 runtime
  内置 flag_gems（零 sgl-kernel 路线，import 面由共享 `sgl-kernel-shim`
  wheel 满足）。落地 = runtime 镜像内两条 pip install 即可执行服务，再叠 app
  层（plugin + shim + deps_app）成 app 镜像。
- **已发布**：metax-maca3.8.1.3 与 ascend-cann9.0.0 的 sglang 0.5.18 app
  镜像均已推 Harbor 并记录
  （[backends/metax.md](sglang-0.5.18/backends/metax.md)、
  [backends/ascend.md](sglang-0.5.18/backends/ascend.md)、
  [sglang-verification-matrix.md](sglang-verification-matrix.md)）。
- **残存约束**：sglang↔runtime torch 版本匹配（torch 由 runtime 矩阵提供，
  wheel 不强制）；每新增后端需走 verify（F/T 双路径 E2E）gate；性能未优化
  （零 sgl-kernel ~4-7 tok/s vs sgl-kernel 基线 ~40）。
