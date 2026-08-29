# Verify Orchestrator（验证编排器）设计

> 目标：把「人在终端里逐个后端验证 + 构建镜像 + 跟进 PR」这条链，收敛成一个
> 自我推进的编排循环。人只做两类事：触发一次、review 它开的 PR。
>
> 状态：设计稿，未实现。分阶段落地见 §7。

## 1. 目标与需求映射

一次触发，编排器驱动 6 个 app（vllm0.20.2 / vllm0.24.0 / megatron_training /
megatron_rl / sglang / verl）× configs.yaml 枚举的每个后端，逐 cell 走通
「验证 → 构建 app 镜像 → 记录 tag → 按规则提 PR」，进度实时落回
`status_matrix.*.yaml`。人不当 driver、不当 monitor。

| 需求 | 落点 |
|---|---|
| 并行验证多 app × 多后端 | driver 的 verify 矩阵 job（§4.1） |
| 可落地场景 E2E 后构建镜像 | verify ✅ → 自动链 `*-app-image.yml`（§3） |
| flagos-ai 问题按规则提 PR + 记链接 | Claude worker 开 draft PR → 回写 `prs:`（§4.2） |
| 进度汇总到独立 yaml | `status_matrix.*.yaml`（已有 4 个，补 sglang/verl） |
| 减少 compact / 数据传输 | Worker contract 零膨胀（§5） |

## 2. 现状（复用，不重建）

以下设施已存在，编排器只在其上做编排，不重写：

| 能力 | 现有载体 | 复用方式 |
|---|---|---|
| 状态唯一真相 | `packaging/*/status_matrix.<app>.yaml` | driver 读 ⬜ 集合、回写符号/`prs:`/`image_tag` |
| 验证脚本 | `verify-vllm-backend.sh`、`verify-megatron-backend.sh` | verify 阶段（§4.1） |
| app 镜像构建 | `.github/workflows/{vllm,megatron}-app-image.yml` | ✅ → 自动触发该 workflow（push） |
| tag 回写 + PR | `scripts/record_app_image_tag.py` | 构建后复用 |
| 矩阵渲染 | `scripts/render_status_matrix.py` | record 阶段复用 |
| 漂移 → 修复 PR | `.github/workflows/status-matrix-consistency.yml` | 兜底复用 |
| 矩阵生成 | `scripts/generate_matrix.py --app` | plan 阶段复用 |

schema 约定见 `docs/status-matrix.md`。关键不变式：

- `image_tag` 存在 ⟺ 该后端已发布（单一事实源）。
- `deps_app` key 存在（configs.yaml）⟺ 该 app 在该后端已验证、可构建。
- `prs:` 是上游 PR 链接的落点（本仓库设施 PR 不放这里）。
- 单元格符号：✅ 通过 / ❌ 失败有结论 / ⛔ 上游阻塞 / ？ 不确定 / ⬜ 待验证 / — 无此编译器。

## 3. 总体架构

```
                 status_matrix.*.yaml（唯一真相）
                       ▲ 读 ⬜ / 回写符号 + prs + image_tag
                       │
     ┌─────────────────┴──────────────────────┐
     │                                        │
  GH Actions driver（确定性，无 claude）      本地 debug-loop（Mac，有 claude）
  .github/workflows/verify-driver.yml        scripts/verify-debug-loop
  ─────────────────────────────────          ────────────────────────────
  plan → verify（节点，脚本，并行）             poll 矩阵 + 队列 ─ 取 ❌ 待调试 cell
          ├ ✅ → 触发 app-image 构建            └ fork claude -p worker
          │        push + 记 image_tag           （ssh → 节点复现/定位）
          └ ❌ → 写失败摘要 → 队列               └ 结构化结果 → 开 PR + 回写
                                                   （prs: 链接 / ⛔ / 修好 → 待重验）
  record → 渲染 + 提交队列 + 开 review PR
```

两条循环靠矩阵 YAML 与 debug 队列交接。claude 不装在节点上——需要 claude 的
环节（失败调试）只在本机发生，通过 ssh 触达节点。

循环自我推进，直到所有 cell 落入终态（✅ / ❌ / ⛔ / ？），或本轮无任何进展。

## 4. 新增组件

### 4.1 driver — `verify-driver.yml`（核心新件）

单个编排 workflow，job 拆解：

1. **plan**（ubuntu）：读 6 个矩阵 YAML，收集所有 ⬜ cell——每个 ⬜ 的编译器列
   （F 和 T 各自，`—` 或终态符号跳过）产出一个 cell，产出
   `{app, backend, compiler(T/F), image, verify_script}` 的 matrix JSON。
2. **verify**（self-hosted，matrix over pending cell，`fail-fast: false`）：
   跑对应 app 的 verify 脚本，driver 把 cell 的编译器以
   `--compiler flagtree|triton` 传给脚本（F→flagtree、T→triton），**完整 E2E
   模式**——脚本真正跑起工作负载并要求
   exit 0，✅ = 「工作负载跑通」，不是「install + import 通过」：vllm 是
   `vllm serve` 返回真实 completion（HTTP 200 + 非空 `choices[0].text`），
   megatron_training 是 mock-data `pretrain_gpt` 5-iter exit 0，二者均非
   `--app-image` 快照模式。失败时写失败摘要（§5.2），成功则标 ✅。megatron_rl
   暂不收集——GRPO 配方上游阻塞（MLF #116 + flash-attn wheel），rl cell 标 ⛔，
   待上游落地后再翻回 ⬜。
3. **queue**（ubuntu，needs verify）：对 verify ❌ 的 cell 生成任务卡 + 失败摘要
   （§5.1/§5.2），写入 `.github/verify-queue.yaml`（§4.2.1）。**不在此调
   claude**——claude 只在本机，调试由本地 debug-loop（§4.2）接手。
4. **build**（needs verify）：对 verify ✅ 的 cell，触发既有
   `{vllm,megatron,sglang,verl}-app-image.yml`（`push=true`），该 workflow 自己
   完成构建 → 快照验证 → push → `record_app_image_tag.py` 回写 tag + 开 PR。
5. **record**（ubuntu，needs build + queue）：重渲矩阵、提交队列文件，把本轮可
   确定的符号 + `prs:` 变更开成 review-gated PR（复用 `record_app_image_tag.py`
   的 PR 机制与 `status-matrix-consistency.yml` 的 dup-PR 检查）。
6. **terminate**（needs record）：汇报剩余 ⬜ 数并结束。**不自动重触发**——cell 的
   符号只随「修复 PR merge 进 main」才真正前进；`record` 落的是
   `auto/verify-results-*` 分支 + draft PR，从不改 main 的 ⬜，所以无改动就重
   dispatch 是空转循环。下一轮由人工 dispatch，或 debug-loop 在修复落地后触发。

driver 的边界：只开 draft / review-gated PR，不合并、不 push main、不 release、
不决定上游合并时机。所有落库动作都走 PR，符合规则 6（>5 行 → PR）与规则 20
（不自行合并 plugin PR）。

### 4.2 Claude debug-loop（本地 Mac，ssh 到节点）

claude 只装在本机（Mac），节点上不装。所以「失败 cell 调试」这一需要 claude 的
环节不在 GH Actions 里，而是本机的一个 debug-loop。它由两部分组成：

**debug-loop（调度，本机）**：`scripts/verify-debug-loop`（launchd 常驻；单轮
tick 短而幂等）。每 tick：poll 队列 + dispatch worker + 回写结果 + 停滞检测，
然后睡到下一 tick。**tick 本身永不阻塞**——异步动作只登记 `pending + poll`，
不等待（§5.5）。

1. `git fetch` 拉最新 main，读 debug 队列（§4.2.1）——由 driver 在 verify ❌ 时
   写入。
2. 对每个待调试 cell，`claude -p <任务卡>` fork 一个 worker（本地进程，并行，
   并发受节点设备占用约束，见 §8）。
3. 收集 worker 的结构化结果（§5.3）：本仓库改动 → 开 draft PR；上游 PR →
   记录链接；把符号 + `prs:` 提交到矩阵分支并开 review PR；从队列移除该 cell。
   结果为 `pending + poll` 的 cell 保留在队列，下一 tick 按 poll 规格查终态。
4. 停滞检测（§5.5.4）：超 deadline 无进展 → 重排队或告警。队列清空则本轮
   结束；driver 的重触发会继续扫剩余 ⬜。

**worker（执行，claude 进程）**：`claude -p` 无头，`--allowedTools` 锁死，输入
是预压缩的任务卡（§5），不是整个 repo。worker 用本机已有的 ssh 别名连到节点
复现（规则 22：ssh 后 su - 非 root；docker exec 进容器），不在节点上跑 claude。

职责（按序）：

1. 读失败摘要，`grep` 定位行，`docker exec` 复现——绝不 `cat` 完整日志。
2. 分类：
   - **本仓库可修**（configs.yaml / Containerfile / verify 脚本）→ 改到独立
     分支，开 draft PR。
   - **上游 bug**（plugin / FlagTree / FlagGems / vllm 本体）→ 按规则 9 在该
     repo 开 draft PR，返回链接。
   - **无法定论** → 返回 `❌ + 结论`，不重试。
3. 产出结构化结论（§5.3），由 debug-loop 回写矩阵（符号 + `prs:`）。

认证：worker 用本机 claude 的既有登录（OAuth / API key），不需要把凭据放到
runner 或节点上；本机 ssh 凭据沿用既有 `~/.ssh/config`，不加新 secret。

#### 4.2.1 debug 队列（driver → loop 的交接面）

driver 在 verify ❌ 时把失败 cell 的**任务卡**（§5.1，含失败摘要）写入
`.github/verify-queue.yaml`（连同当轮 record PR 一起提交）。debug-loop 消费这个
队列、逐个解析并回写终态；矩阵 YAML 只保留终态符号，不存中间失败摘要——这样
矩阵干净、队列即「待 claude 处置」的暂存区。

### 4.3 sglang / verl 脚手架（绿地）

二者各有 1:1 的仓内模板，逐文件复制（不是抽象参考）：

| 新 app | 模板 | 上游 plugin repo | 验证形态 |
|---|---|---|---|
| sglang | `packaging/vllm/` 全套 | `flagos-ai/sglang-plugin-FL` | install sglang + plugin → `sglang serve` + completion + 快照 |
| verl | `packaging/megatron/` 全套 | `flagos-ai/verl-FL` | 单步 install → import + pybind 扩展断言 |

每 app 需新建：`packaging/{sglang,verl}/`（含 `status_matrix.<app>.yaml` +
`verify/verify-<app>-backend.sh`）、`app/{sglang,verl}/Containerfile`、
`.github/workflows/{sglang,verl}-app-image.yml`、configs.yaml `deps_app.<app>`。
PR 归属分流：plugin bug → `sglang-plugin-FL`；内核/扩展 bug → `verl-FL`
（与 vllm → `vllm-plugin-FL`、megatron → `Megatron-LM-FL` 的分流逻辑一致）。

### 4.4 schema 扩展（`type` 枚举）

矩阵 schema 的 `type` 当前是 `megatron | vllm`。加 sglang / verl 不是「多建两个
yaml」，而是扩枚举，连带触碰：

- `scripts/render_status_matrix.py`：type → 渲染目标 md 的映射。
- `docs/gen_data.py` / `docs/gen_descriptions.py`：`app_published_tag()` 与
  `plugin_package` 反推。
- configs.yaml `deps_app.sglang` / `.verl`。
- 渲染目标新增 `packaging/sglang/docs/sglang-verification-matrix.md`、
  `packaging/verl/docs/verl-verification-matrix.md`（含 marker 块）。

场景 sid：sglang = `inference`（同 vllm）；verl = `training` / `rl` /
`post_training` / `inference`（同 megatron）。

## 5. Worker contract（零膨胀）

并行总传输 ≈ worker 数 × 单 worker 上下文。compact 的根因是单次上下文超窗口，
并行只是让它发生更多次。约束单次 → 单次 ≤ 任务卡 + 按需 grep + ~10 行结果，
远在窗口之下。

### 5.1 任务卡（worker 输入，30–60 行）

driver 为每个失败 cell 生成一张卡，worker 从零开始只拿卡：

```yaml
cell:        vllm0.24.0 / cambricon-neuware4.4.3 / T
image:       harbor.../flagos-runtime-cambricon-neuware4.4.3:2.1.2
verify_script: packaging/vllm/verify/verify-vllm-backend.sh
failure:     # 预压缩摘要，见 §5.2
  step:      serve
  exit_code: 1
  error_head: "RuntimeError: ..."   # 前 20 行
  error_tail: "..."                 # 后 20 行
log_path:   /tmp/verify-<cell>.log  # 完整日志留节点，不进上下文
pr_rules:   <canned 片段：全英文 body / 无 trailer / 单 disclosure / 先 fetch main>
```

PR 规则（规则 9）作为 canned 片段注入，不塞整本笔记。

### 5.2 失败摘要（verify 脚本产出，零模型成本压缩）

verify 脚本失败时写结构化摘要，而非让 worker 读完整日志：

```yaml
cell / app / vendor_backend / image / step / exit_code /
error_head / error_tail / log_path
```

对已有 vllm / megatron verify 脚本是加法改动；sglang / verl 从第一天就带。

### 5.3 结构化结果（worker 输出，~10 行）

worker 不回散文报告，只回 driver 可直接解析的结构：

```yaml
verdict:   upstream-bug | fixed-local | need-pr | no-conclusion
root_cause: "paged_attention_v2 (blk=256,hs=96) 静默不写"   # 一行
symbol:    ⛔
note:      "见 FlagGems #5xxx"
pr:        https://github.com/flagos-ai/.../pull/NNN   # 或 null
```

### 5.4 会话纪律

- 每 cell 一个 worker，做完即死；`--max-turns` 锁死。
- 同一 cell 重试才 `--resume`（增量），不重发历史。
- debug-loop 只取 `--output-format json` 的 `result` 字段，永不读 subagent 的
  JSONL 全量 transcript（那是溢出源）。

### 5.5 No-idle-wait（空转防治）

根本约束：**任何「等待 workflow / 脚本返回」都不允许是阻塞等待。** 历史教训
（用户反馈）：agent 发出动作后进入空等，几十分钟无进展，须人工提醒才继续查。
作为 loop 与 worker 的第一纪律，不靠自觉，靠结构。

1. **区分同步快 / 异步慢。** 同步（grep、`docker exec` import、快照对比，分钟
   级）允许前台阻塞；异步（serve 测试、docker build、`gh workflow run`）一律
   后台起，随即进入 poll，绝不前台阻塞。

2. **异步句柄显式化 + 完成哨兵（对治「监测错位置 / 漏退出信号」）。** 空转最
   常见的直接原因不是「等待」本身，而是 agent 的**执行失误**：本该在节点上监听
   `/tmp/xxx`，却在本地 macOS 上监听；进程已结束，agent 没捕到退出信号，死等。
   两个结构约束杜绝这类失误：
   - **句柄落到坐标**：worker 发起异步动作时，`pending + poll` 必须写明 `host`
     （ssh 别名）+ 该 host 上的绝对 `log_path` + 进程 PID；loop 下一 tick 的 poll
     命令**通过该 ssh 别名在目标 host 上执行**，绝不在 worker 本地（macOS）上下文
     里 `ls /tmp`。监测位置与动作运行位置由同一句柄锁定，不靠 worker 记性。
   - **完成哨兵（sentinel）**：异步动作退出时（含失败/崩溃，用 `trap EXIT` 或
     `wait; echo $? > marker`）把退出码写到该 host 的一个已知绝对路径。poll 只查
     「哨兵文件是否存在于该 host 该路径」——进程只要结束就必写哨兵，poll 不可能
     漏掉「已结束」的进程。查哨兵存在性而非 grep 成功文本，从根上消灭「进程结束
     但没捕到信号」。

3. **poll 带 deadline + 覆盖全部终态。** 每次等待是 `until … ; do sleep N;
   done` 且有 max-time；poll 条件匹配成功签名 AND 失败签名（Traceback / Error
   / FAILED / Killed / OOM）AND 超时。只匹配成功 = 崩溃看起来和「还在跑」一样
   —— 这正是空等的来源。

4. **loop 自驱动，不等人。** 异步动作的结果不在同一次调用里等：worker 把
   `pending: <动作>` + `poll: <何时/如何查>` 写进队列就返回；loop 下一 tick
   再查。循环的再入是 launchd 的 tick，不是人工提醒。

5. **心跳 / 停滞检测。** 队列条目带 `last_progress` 时间戳 + deadline；超
   deadline 无进展 → loop 视为停滞，重排队或告警，绝不静默挂起。这直接对应
   「几十分钟没进展」：无进展超时是信号，不是常态。

worker 回合结束约定：每条结果必以终态符号（✅/❌/⛔/？）或
`pending + poll` 结束，**禁止以「等待中」结束**。

## 6. Cell 状态机

```
⬜ ──verify──► ✅ ──build/record──► image_tag 落库（终态）
⬜ ──verify──► ❌ ──debug──► fixed-local / need-pr ──► 开 draft PR ──► 重跑 verify
                        └─► upstream-bug ──► draft PR + prs: 链接 ──► ⛔（终态）
                        └─► no-conclusion ──► ❌ + note（终态）
```

终态 = ✅（带 image_tag）/ ⛔（带 prs）/ ❌（带 note）/ ？。驱动终止条件只看
「是否还有 ⬜ 且本轮有进展」。

## 7. 分阶段实施

- **Phase 0**：本文档（已完成）。
- **Phase 1**：driver + debug-loop + worker contract，接线已有 4 app。先在一
  小片后端（nvidia-cuda12.8 + 一个非 nvidia 后端）跑通完整闭环，再铺全量。此
  阶段确定 debug-loop 的常驻方式（launchd / cron / 手动常驻）与 worker 权限白名单。
- **Phase 2**：sglang / verl 脚手架（§4.3）+ schema 枚举扩展（§4.4）。

## 8. 风险与处置

| 风险 | 处置 |
|---|---|
| 死循环 / 失控重触发 | terminate 不自动重触发（无改动即停）；仅人工 dispatch 或 debug-loop 修复落地后触发；保留手动停开关 |
| self-hosted runner 争用（规则 14） | 并发上限；短 job（record/plan）先于长 job（verify/build）；复用 build-config.yml 的 per-vendor runner pin |
| worker 违规开 PR（规则 9） | canned PR 规则片段 + worker 内建开 PR 前检查单；只开 draft，人转正 |
| worker 上下文膨胀 / compact | §5 worker contract |
| vllm-plugin-FL / sglang-plugin-FL PR 合并权限（规则 20） | worker 只开 PR + request review，不合并；deps_app 依赖未合并 PR 时 cell 标 ⛔ |
| worker 无结论 cell 堆积 | no-conclusion 是终态，不重试 |
| 凭据泄漏（规则 0） | worker 不回显 secret；代理配置不进任何可监听位置（规则 22） |
| deps_app 写入路径 | 是 configs.yaml 变更 → 走 review PR（driver 开 draft），不直写 |
| claude 不在节点 → 调试只能本机 | 架构按此拆分：driver 不调 claude，调试由本地 debug-loop ssh 到节点；不试图在 runner/节点装 claude |
| 节点设备争用（stale 容器静默占设备） | debug-loop 并发上限；每 cell 独立持久容器，结束即 rm（规则 12） |
| 本机 loop 掉线 → 队列堆积 | 队列是仓库文件，可断点续跑；同 cell 重试走 `--resume`（增量） |
| worker 空等（前台阻塞 / fire-and-forget / 静默挂起 / 监测错位置 / 漏退出信号）| §5.5 no-idle-wait：异步句柄显式化（host+路径+PID）+ 完成哨兵 + 带 deadline 的 poll 覆盖全部终态 + 停滞检测重排队，回合必以终态或 pending 结束 |

## 9. 后续追踪

- debug-loop 常驻方式（选定 launchd）已定；单轮 tick 间隔、并发上限、停滞
  deadline 阈值在 Phase 1 落地后回填 §4.2 / §5.5。
- sglang / verl 的 plugin repo PR 合并权限假设与 vllm-plugin-FL 一致（规则 20），
  落地前与 plugin 团队确认。
- verl 场景 sid 是否真需要 `training/rl/post_training/inference` 四列，待 verl
  实际验证形态确定后收敛（可能只需 1–2 列）。
- 后端口径：以 configs.yaml 实际枚举为准（当前 19，iluvatar-corex4.5.0 在途），
  driver 不写死数字。
