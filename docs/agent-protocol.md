# Agent 写作/记录协议（agent-protocol）

> 本文件是 agent 在本仓库内**写什么、不写什么**的唯一权威规则。
> 新会话开箱即读（CLAUDE.md「Agent collaboration discipline」指向本文件）。
> 背景：多 app × 多后端 × F/T 双路径的 agent 驱动验证（约 200 个 case），
> 见 `docs/verify-orchestrator.md`。知识层失控 → 本协议（2026-08-31 立）。

## 1. 知识三层分类

| 层 | 归属 | 生命周期 | 举例 |
|---|---|---|---|
| 经验总结 | `packaging/<app>/docs/` | 常驻（git 跟踪） | 后端验证记录、playbook、decisions、status matrix |
| 工作文件 | WORKING-CONTEXT 类 | 有时效：创建 → 使用 → 并入 docs → **删除** | verl WORKING-CONTEXT |
| 流水账 | 禁止 | 不落盘 | "GPU 显存不足→停容器→问题消失" |

**准入门判定**（写之前问一句）：
> 这条知识是否会让**另一个 agent/会话**跳过一步发现？不会 → 不写。

- 只记结论（为什么 / 最终状态 / 机制），不记过程（发生了啥 / 试了几次）。
- 环境事件只有影响结论时才值得写。

## 2. Subagent 写权限协议

- subagent 只产出两类东西：
  1. 报告（固定 schema 或短文本）
  2. 代码改动（明确授权的编码任务）
- subagent **永不写 docs / memory / WORKING-CONTEXT**。写入判断由主会话执行
  ——主会话有全局 view + 规则，subagent 只有局部任务。
- 主会话对 subagent 报告的处置：有价值 → 由主会话写入；无价值 → 丢弃，不落盘。
- 例外需显式授权（如"记录到 X 文件"是任务本身的一部分）。

## 3. 输出克制（注释纪律）

- 注释只解释**为什么**（决策、陷阱、权衡），不解释**是什么**（代码自明）。
- 注释密度匹配周围代码；不写学习笔记式注释。
- 依据：每条注释每次 read-back 都进 context——100 行代码 100 行注释
  = 双倍负担。

## 4. 索引即入口

- 每线 `docs/README.md` 是唯一入口；agent 只读入口 + 点到的文件，不整扫目录。
- 先 grep 定位再读最小片段；大文件不整读。
- 文档移动/删除必须同步 README（沿用 `packaging/README.md` 引用维护清单）。

## 5. 工作文件时效规则

- WORKING-CONTEXT 类文件生命周期 = 创建 → 使用 → 任务完成并入
  docs/status matrix → **删除**。
- 同一知识出现两份副本 → 以入库版为权威，删除副本（verl 案例即为反例）。
- 删除前检查：
  - `git ls-files` 确认是否入库；gitignored 文件删除 = 真丢失，先确认内容已并入。
  - 删除动作不赶时机：文件仍在使用就保留（verl 线案例）。
