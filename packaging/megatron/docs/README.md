# megatron app 验证文档

megatron-core（Megatron-LM-FL fork）应用镜像（`megatron_training` /
`megatron_rl`）的验证记录，按版本拆目录。

## 入口

| 文档 | 内容 |
|---|---|
| [megatron-verification-matrix.md](megatron-verification-matrix.md) | 验证状态矩阵（场景 × 编译器 × 后端；状态块由 `scripts/render_status_matrix.py` 自动重写，矩阵内外的 wiki 链接为手写 prose） |
| [megatron-0.17.1/index.md](megatron-0.17.1/index.md) | 0.17.1 版验证报告入口：背景、后端索引、版本级结论/遗留 |
| [megatron-0.17.1/playbook.md](megatron-0.17.1/playbook.md) | 标准流程（wheel 构建 + app 镜像 + 节点 verify）与弯路记录 |
| [megatron-0.17.1/decisions.md](megatron-0.17.1/decisions.md) | 自动化边界、风险痛点、ADR |
| [megatron-0.17.1/report-builder.md](megatron-0.17.1/report-builder.md) | wheel 构建报告（`builder/` 产出） |

## 各版本目录结构

```
megatron-0.X.Y/
├── index.md              # 背景 + 后端索引表 + 版本级结论/遗留
├── playbook.md           # 标准流程 + 弯路记录
├── decisions.md          # 自动化边界 + 风险痛点 + ADR
├── report-builder.md     # wheel 构建报告（builder/ 产出）
└── backends/             # 每后端一节验证记录（<vendor>.md）
```

## 其他目录

- `memory/`：agent 工作记忆（2026-08-13 用户指定位置），非交付文档。
