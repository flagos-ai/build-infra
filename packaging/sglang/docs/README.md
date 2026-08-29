# sglang-plugin-FL 打包调研

入口文档。

| 文档 | 内容 |
|---|---|
| [sglang-release-packaging-research.md](sglang-release-packaging-research.md) | sglang-plugin-FL 打包成发布镜像的调研：与 vllm-plugin-FL 的对比、仓库结构、各后端 CI 镜像版本矩阵、插件架构与验证要点（三层替换机制 / 参考环境对照 / 验证配方）、打包模型分析与待决策 |
| [zero-sgl-kernel-arch-20260828.html](zero-sgl-kernel-arch-20260828.html) | 零 sgl-kernel 方案架构图（本地 HTML）：目标架构四层路由 + 逐 vendor 迁移面分级 + 封装分发落地形态（统一 runtime + 单步安装）|
| [zero-sgl-kernel-feasibility-20260828.md](zero-sgl-kernel-feasibility-20260828.md) | 零 sgl-kernel 可行性定案：flagos 默认路径已零依赖（6 op 全走 flag_gems），迁移面=vendor backend 约 2/3 op 有覆盖，缺口 enflame 4 op + kunlunxin klx_* + ascend sgl_kernel_npu |
| [sglang-0.5.18/backends/metax-0.5.12.md](sglang-0.5.18/backends/metax-0.5.12.md) | 0.5.12 零 sgl-kernel 参考记录（0.5.18 方案的前身实证：路线可行性闭环 + 完整根因链）|
| [metax-sgl-kernel-wheel-e2e-20260828.md](metax-sgl-kernel-wheel-e2e-20260828.md) | 0.5.10 自编 sgl-kernel 子集 wheel 验证记录（对比基线，已被零 sgl-kernel 路线取代）|
| [notes-cuda128-e2e-20260827.md](notes-cuda128-e2e-20260827.md) | 0.5.10 cuda12.8 F/T 双路径 E2E 验证原始记录（前身实证，历史/调研）|
| [sglang-0.5.18/](sglang-0.5.18/) | **0.5.18 per-vendor wheel 打包验证报告**（index / playbook / decisions / backends）|

## 结论速览

- **plugin 层**：与 vllm-plugin-FL 同构（OOT plugin + 运行时单步安装），成本低。
- **打包模型（2026-08-28 定案）**：统一 runtime + 单步安装（per-vendor
  wheel）。每个后端在自己的 runtime `-build` 镜像内从同一 sdist
  （`sglang-0.5.18.tar.gz`）构建 wheel；srt_empty 非 CUDA variant 基座天然
  零 torch 零 sgl-kernel，repack 仅打 `+flagos` 后缀；硬件算子收敛到 runtime
  内置 flag_gems（零 sgl-kernel 路线）。落地 = runtime 镜像内两条 pip install
  （`sglang==0.5.18+flagos` + `sglang-plugin-FL`）即可执行服务。
  已实证：metax maca3.8.1.3 0.5.18 F/T 双路径 E2E 全过
  （[sglang-0.5.18/backends/metax.md](sglang-0.5.18/backends/metax.md)）。
- **残存约束**：sglang↔runtime torch 版本匹配（torch 由 runtime 矩阵提供，
  wheel 不强制）；ascend aarch64 依赖闭包（llguidance 等 Rust 编译包）与
  rust aarch64 工具链缓存待实证（[sglang-0.5.18/decisions.md](sglang-0.5.18/decisions.md)
  §5.6）；metax 零 sgl-kernel 性能 ~4 tok/s（sgl-kernel 基线 ~40）未优化。

状态：调研完成（2026-08-26）→ 零 sgl-kernel 可行性定案（2026-08-28）→
0.5.18 per-vendor wheel 打包落地中（metax 已闭环，ascend aarch64 待构建）。
