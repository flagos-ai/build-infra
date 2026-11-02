# docs/ — 知识层入口

本文件是 agent 与人查找本项目知识时的**唯一入口**。先在这里定位，再读点到的
最小片段；不要整目录扫描。

写作规则与两条硬规则（技能不装事实 / 家的选择由变化轴决定）见
[`agent-protocol.md` §1.1](agent-protocol.md#11-两条硬规则决定写在哪)；本文件只
回答「东西在哪」。

## 路由表

| 要查的东西 | 去哪 |
|---|---|
| 仓库契约：命名、数据流、层链、约定 | `CLAUDE.md` |
| 校验矩阵数据源与符号语义 | [`status-matrix.md`](status-matrix.md) |
| 验证编排器设计（driver / worker 契约） | [`verify-orchestrator.md`](verify-orchestrator.md) |
| 镜像 changelog 规则与发布线 | [`changelog.md`](changelog.md) |
| 发版流程 | [`release-workbook.md`](release-workbook.md) |
| wheel 目录与源码包信息的记录机制 | [`wheel-info.md`](wheel-info.md) |
| runner 的 Docker/containerd 数据目录迁移 | [`runner-disk-migration.md`](runner-disk-migration.md) |
| 某应用某版本的验证历史 | `packaging/<app>/docs/<app>-<ver>/`（入口是该目录的 README） |
| 某打包线的设计（为什么这样做） | `packaging/<comp>/DESIGN.md`（跑法看同目录 README） |
| 某厂商的平台事实（设备、工具链、坑） | [`vendors/<vendor>.md`](vendors/)（怎么收见该目录 README） |
| 脚本索引 | `scripts/README.md` |
| 打包目录骨架与引用维护清单 | `packaging/README.md` |
| 流程技能（做什么、何时停下问） | `.claude/skills/`，按 frontmatter 的 Trigger / NOT-for 选择 |

## 生成物，勿手工索引

`base/`、`runtime/`、`app/*/`、`docs/content/` 是 `scripts/docs/gen_descriptions.py`
的产物（`configs.yaml` → `docs/data/images.yaml` → 页面与仓内 readme）。改内容请改
生成器或数据源，不要在这些目录加索引文件或手写正文。生成器拒绝覆盖没有
provenance 标记的页面，手写页请另起名字。

`docs/content/` 是 Hugo 站点（`contentDir: content/en`），面向用户而非 agent；
本文件的规则不约束它。

## 索引校验

知识层的四条索引规则（workflow 表齐全、技能边界与路径可解析、无孤立文档、厂商页
齐全）由 `scripts/docs/check_knowledge.py` 校验 —— 规则原文在该脚本的文件头。
CI 在 `.github/workflows/knowledge-index.yml`。规则背后的纪律是
[agent-protocol.md §4](agent-protocol.md#4-索引即入口)：**每线 README 是唯一入口，
其他文档必须从某处的索引可达**。新增一个不进索引的文档，这个检查会拦下来。

## 待落地（知识层重构，2026-11-01）

- **P1**：`packaging/*/docs/**` 的 39 个后端记录里，厂商范围内容改为引用
  `docs/vendors/`（随各线下次验证顺手改，不单独开批）。
- **P4**：仓库外 user memory 里的项目状态类文件迁入本仓库对应 docs（仓是公开的，
  迁入前必须脱敏：凭证、代理地址、内网拓扑、`/home/<user>` 路径一律不入库）。
