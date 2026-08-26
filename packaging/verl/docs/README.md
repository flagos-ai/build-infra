# verl app 镜像（verl-FL）— 实施计划

入口文档。

| 文档 | 内容 |
|---|---|
| [verl-app-image-plan.md](verl-app-image-plan.md) | 在 runtime 镜像之上制作 verl app 镜像的实施计划：verl wheel 构建设施、Containerfile 设计、configs.yaml 变更、docs 管线 hooks、CI workflow、verify 脚本与风险清单 |

## 结论速览

- **安装方式**：构建 verl wheel 发版（`packaging/verl/builder/` + `verl-wheel.yml`，镜像 megatron 路线）。
- **关键约束**：verl 自身必须 `--no-deps` 安装——`numpy<2.0.0` 与 runtime `numpy==2.3.5` 冲突，依赖显式钉版本。
- **app 键名**：`verl0.7.0`（版本入键名）→ 镜像 `flagos-app/verl0.7.0-{vendor}-{backend}:{stack_version}-{fork_ver}`。
- **rollout vllm**：verl-FL 自带 vllm 0.11/0.12 线（非 build-infra 的 0.20.2/0.24.0 repack）+ vllm-plugin-fl wheel。
- **后端范围**：全部 17 个可构建后端；节点 verify 需 F（flagtree）/ T（triton）双路径。

状态：实施计划（2026-08-27 已确认）。执行进度见 `packaging/verl/WORKING-CONTEXT.md`（工作文件，不提交 git，任务收尾后删除）。
