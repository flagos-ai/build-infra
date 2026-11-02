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

## 待落地

- **P1**：`packaging/*/docs/**` 的 39 个后端记录里，厂商范围内容改为引用
  `docs/vendors/`（随各线下次验证顺手改，不单独开批）。

### docs 生成管线

- **并发 race 会掉包版本**：`auto/base-descriptions` 上两个并发 run 会丢包版本记录
  （git、vim），因为 accumulate job 只合并当前 run 的 artifact；单次干净 run 结果
  正确。低优先，workaround = 不并发手动触发。
- **`docs/data/images.yaml` 位置太隐蔽**：它是 `gen_data.py` 的产物、喂
  `gen_descriptions.py` 与 `extract_versions.py`，git-ignored 且藏在子目录下，
  新贡献者发现不了。重构时移到显眼位置，并同步所有引用点
  （`gen_data.py`、`gen_descriptions.py`、`extract_versions.py`、`verify_base.py`、
  `missing_versions.py` 及 workflow）。
- **`status_matrix.<app>.yaml` 布局**：验证格在顶层
  `scenarios.inference.verification`，而设施布尔（`deps_app` / `launch_docs` /
  `image_tag` / `prs`）在 `backends.<backend>`，同一个后端的状态被劈成两处。
  目标是把 {T,F} 并进 `backends/<backend>`；联动面 = `render_status_matrix.py`
  读逻辑、`record_image.py` 的行编辑定位、`verify-*` record 脚本、
  `docs/status-matrix.md` schema、`gen_data.py`。改动时保留 `note` 列语义
  （见 `docs/status-matrix.md`）。

## 已收口

- **P4（仓库外 memory 迁仓）—— 2026-11-02 完成。** 结论：**这批文件多数不是"待迁入"，
  而是仓库文档的副本**。逐条比对后，仓库里没有的那些已按变化轴各归其位：厂商事实 →
  `docs/vendors/`，机制 → 对应组件的 `DESIGN.md` / `WHEEL-DESIGN.md`，仓库契约 →
  `CLAUDE.md`，待办 → 本文件的待落地节；其余要么已在本仓库
  （逐后端记录、`packaging/*/DESIGN.md`、`docs/vendors/`、`configs.yaml` 注释），
  要么是**会话状态**（进行到哪、谁在做哪条线）——后者本就不该进 memory，
  见 [`agent-protocol.md` §7](agent-protocol.md#7-仓库外-memory-的边界)。
  新增的 §7 同时给出边界：memory 是按工作目录共享的，不能当多会话的协调面。
  收尾时 memory 从 22 个文件降到 4 个。
