# packaging/ — 应用镜像打包资料

`packaging/` 下四个应用（vllm / megatron / sglang / verl）的镜像打包资料
收敛到同一骨架。本文件是目录结构约定与引用维护清单——**移动文件必须同步
文末清单所列引用点**。

## 目标骨架

```
packaging/<app>/                          # app = vllm | sglang | megatron | verl
├── config.yaml                           # repack 分类规则（仅 repack 型：vllm、sglang）
├── build-and-repack.sh                   # wheel 构建（vllm、sglang）
├── build-sdist.sh / merge-runtime-base.py   # sglang 特有（sdist 构建链）
├── builder/                              # fork 源码 wheel 构建设施（megatron；verl 未来同款）
├── verify/verify-<app>-backend.sh        # 节点验证脚本（统一 verify/ 子目录）
├── status_matrix.<appkey>.yaml           # 矩阵数据源（docs/status-matrix.md 既有约定）
├── wheels/                               # 构建产物（*.whl，gitignore）
└── docs/
    ├── README.md                         # 入口索引（每个 app 必须有）
    ├── <app>-verification-matrix.md      # 矩阵渲染目标（render_status_matrix.py 既有约定）
    ├── handoffs/                         # vendor 交接报告（vllm 已有）
    ├── memory/                           # agent 工作记忆（megatron 特有，2026-08-13 用户指定）
    └── <app>-<version>/                  # 每版本验证报告
        ├── index.md                      # 背景 + 后端索引 + 版本级结论/遗留
        ├── playbook.md                   # 标准流程 + 弯路记录
        ├── decisions.md                  # 自动化边界 + 风险痛点 + ADR
        └── backends/<vendor>.md          # 每后端验证记录
```

## 命名规则

- **文档目录 `<app>-<version>` 带连字符**：`vllm-0.20.2`、`megatron-0.17.1`。
- **app 键 `<app><version>` 不带连字符**：`vllm0.20.2`、`megatron_training` /
  `megatron_rl` —— 是 workflow 输入、Harbor repo 段、status_matrix 文件名的
  唯一事实源，**保持现状不改**。
- **状态矩阵**：`status_matrix.<appkey>.yaml` 是数据源（人工只改 YAML），
  `docs/<app>-verification-matrix.md` 是渲染目标——marker 块由
  `scripts/render_status_matrix.py` 重写，marker 外的手写 prose（含 wiki
  链接）保留。新增组件时在渲染脚本 COMPONENTS 注册。

## 各 app 变体

| app | 打包模型 | 特有文件 | 现状 |
|---|---|---|---|
| vllm | repack（empty 构建 + `+flagos` + 单步安装） | `config.yaml` + `build-and-repack.sh` | vllm-0.20.2 / vllm-0.24.0 已按 per-version 布局 |
| sglang | repack + sdist | 同 vllm + `build-sdist.sh` + `merge-runtime-base.py` | 0.5.18 per-vendor wheel 打包验证中 |
| megatron | fork 源码 wheel（`0.17.1+fl.<date>.g<sha>`） | `builder/` | megatron-0.17.1 已按 per-version 布局 |
| verl | fork 源码 wheel（规划中） | `builder/`（未来） | 实施计划已确认，验证设施未落位 |

`packaging/flagtree/`、`packaging/flaggems/`、`packaging/flash-attn/` 是
runtime 层/编译器 wheel（非四 app，不适用本骨架）；`packaging/script/` 是
共享工具（`repack.py` / `audit-deps.py`），不属任何 app。

## 引用维护清单

移动或重命名下列文件时，必须同步所有引用点：

| 文件 | 引用点 |
|---|---|
| `verify/verify-<app>-backend.sh` | `.github/workflows/<app>-app-image.yml`（调用行 + 注释）；`scripts/verify_collect_cells.py`（`APP_VERIFY` script 字段）；`docs/verify-orchestrator.md`；app 内 playbook/decisions |
| `status_matrix.<appkey>.yaml` | `scripts/render_status_matrix.py`（COMPONENTS 注册）；`docs/status-matrix.md` |
| `docs/<app>-<version>/` 内文件 | 同目录互链（wiki 链接 `[[...]]` 或相对路径）；其他 app 文档；`docs/memory/*.md` |

## 未来落点

- **sglang**：`verify/verify-sglang-backend.sh`、`status_matrix.sglang0.5.18.yaml`
  待验证设施展开时落位（骨架位置已预留）。
- **verl**：`verify/verify-verl-backend.sh`、`status_matrix.verl0.7.0.yaml`、
  `builder/` 待实施计划落地。
- 验证设施按本骨架落位后，更新「各 app 变体」表。
