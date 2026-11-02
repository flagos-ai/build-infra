# vllm repack 验证文档

vLLM 各版本 repack（empty 构建 + `+flagos` + 单步安装）的验证记录，按版本拆目录。

## 入口

| 文档 | 内容 |
|---|---|
| [vllm-verification-matrix.md](vllm-verification-matrix.md) | 验证状态矩阵（每单元格 = 后端 × 版本 × 编译器，仅记录状态；状态块由 `scripts/render_status_matrix.py` 自动生成） |
| [vllm-0.20.2/index.md](vllm-0.20.2/index.md) | 0.20.2 版验证报告（背景、后端索引、决策） |
| [vllm-0.24.0/index.md](vllm-0.24.0/index.md) | 0.24.0 版验证报告（TL;DR、背景、metax 总览、遗留事项） |
| [handoffs/](handoffs/) | 交给厂商/上游的根因报告（每份一个缺陷） |
| [ascend-vllm-0.24.0.md](handoffs/ascend-vllm-0.24.0.md) | 910B app 镜像交付说明（2.1.2 那一版的实测启动命令与检查点） |
| [sunrise-vllm-0.20.2.md](handoffs/sunrise-vllm-0.20.2.md) | PTPU app 镜像交付说明；含 FlagTree 解码挂死的回退与注意事项 |

**本目录是 vllm repack 的唯一事实源。** 记录、进度、开放 PR 一律写在这里，
不另设 memory 文件 —— 2026-08-03 曾因 memory 副本与文档分叉而误导判断。

**VPF PR 的 reviewer 验收 gate** = vllm-plugin-FL 仓的
`tools/adaptation-gate-cases/README.md`（两个模型 × eager/graph）。这是 vllm-plugin-FL
侧的要求；FlagTree 侧从没要求跑别的模型，两套别混用。

## 各版本目录结构

```
vllm-0.X.Y/
├── index.md        # 报告入口：背景、后端索引表、版本级结论/遗留事项
├── playbook.md     # 标准流程（empty 构建 + +flagos + 单步安装）与弯路记录
├── decisions.md    # 决策：自动化边界、风险痛点、ADR、版本推进协作问题
└── backends/       # 每后端一节验证记录（nvidia/metax/mthreads/hygon/…）
```
