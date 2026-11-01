# verl app 镜像（verl-FL）— 实施计划

入口文档。

| 文档 | 内容 |
|---|---|
| [verl-app-image-plan.md](verl-app-image-plan.md) | 在 runtime 镜像之上制作 verl app 镜像的实施计划：verl wheel 构建设施、Containerfile 设计、configs.yaml 变更、docs 管线 hooks、CI workflow、verify 脚本与风险清单 |

## 结论速览

- **安装方式**：构建 verl wheel 发版（`packaging/verl/builder/` + `verl-wheel.yml`，
  镜像 megatron 路线）；纯 Python 包，一个 `py3-none-any` wheel 通吃全部后端。
- **关键约束**：runtime 矩阵统一锁定 `numpy==1.26.4`，verl 的 `numpy<2.0.0` 天然
  满足；numpy/torch/triton/flag_gems 都由 runtime 拥有，deps_app 不含它们。
- **app 键名**：`verl0.7.0`（版本入键名）→ 镜像
  `flagos-app/verl0.7.0-{vendor}-{backend}:{stack_version}-{fork_ver}`。
- **rollout vllm**：verl-FL 自带的 0.11/0.12 线与 vllm-plugin-FL 的 0.13.0 下限
  **交集为空** → 走 fork 侧补丁路线，复用 build-infra 的
  `vllm==0.20.2+flagos` repack wheel（移植清单见计划 §7.1）。
- **TE-FL**：独立纯 Python wheel（`TE_FL_SKIP_CUDA=1`），需新增
  `packaging/transformer-engine-fl/builder/`；flagcx 对 verl 无强依赖。
- **后端范围**：全部 17 个可构建后端；节点 verify 需 F（flagtree）/ T（triton）双路径。

状态：实施计划（2026-08-27 已确认，正文见下表文档）。本文档即该线的入口与进度载体，
未落地的开放项在计划 §7，不再另设工作文件。
