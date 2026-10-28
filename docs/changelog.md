# Image Changelog（镜像变更日志）

> 每层镜像（base / runtime / app）的 tag 只带全局 FlagOS 版本号，粒度很粗；
> 同一个 tag 下镜像内容会持续变化（下层镜像升级、Containerfile 里的包、
> app 装入的 wheel）。changelog 逐镜像记录**对它有意义的变更**——为什么重建、
> 变了什么——而不是机械的版本号跳动。
>
> Per-image changelog. An image tag only carries the coarse, stack-wide FlagOS
> version, yet the image content keeps changing under the same tag (lower-layer
> upgrades, Containerfile packages, the wheel an app installs). The changelog
> records **the changes that matter for that image** — why it was rebuilt, what
> changed — not mechanical version bumps.

## 规则 / Rule

**没有充分理由，不重建镜像。** 重建前必须先在 changelog 写一条待定条目
（reason 与 reason_zh，date 留空）。push 前门禁检查该条目是否存在、两种语言
是否都写了；不满足就拒绝 push。调试构建（`push=false`）不受此限。

**An image is never rebuilt without a documented reason.** Before a rebuild, a
pending entry (reason and reason_zh, empty date) must be added to the
changelog. A push-time gate refuses the push when it is absent, or when either
language is missing. Debug builds (`push=false`) are exempt.

## 文件与结构 / Files and schema

逐镜像一个文件：base 层 `base/changelogs/<backend>.yaml`，
runtime 层 `runtime/changelogs/<backend>.yaml`，
app 层 `app/<app>/changelogs/<image>.yaml`。字段含义见文件头注释：

文件名与文件内的 `image:` 就是镜像名。base 层与 runtime 层用后端 key，`image:`
写完整镜像名；app 层用公开名 `{app}{app_version}-{app_name}`（见
`scripts/app_public.py`），改公开名时两者一起改，**改名不构成重建，不新增
entry**。工作流的 changelog 路径与 gate 都按这个名字找文件，漏改一处即 push
前被拒。

- `tags`：发布过的 tag，按时间**倒序**（最新在前）。已被替换、registry 不再
  保留的 tag 折叠进取代它的那条 entry 的历史叙述里——本文件是它唯一的痕迹。
- `entries`：每次实质构建一条，按时间**倒序**。
  - `date`：registry 的 `push_time`。正常情况下由工作流在 push 后回填，不手写；
    唯一的例外是回溯补写的条目（base 层 2.1.2 / 2.2.0 / 2.3.0 —— 那几次 push
    早于该层有 changelog），日期由人从 Harbor 读回来填。
  - `reason`：本次重建的理由（对该镜像有意义的变更）。人写 **markdown**，
    **一项一条**，只写这一版带来了什么——没变的东西不写，不写 PR 号、不写
    构建流水账、不写与上一版的对比（改了什么是「带来什么」的自然结果，不必
    单说一遍）。理由最终随镜像一起发布，所以多项理由必须可读成一个列表。
  - `reason_zh`：`reason` 的中文版，**同一结构**（一项一条，条数与顺序一致）。
    发布时两种语言都在，所以新条目两个字段都必须写；门禁只检查待定条目，
    因此缺翻译只可能是新写的。**字段出现之前**已交付的 464 条是事后补译的
    ——它们的英文仍是权威，中文只是同一份理由的另一种语言，不是新理由。
    可继续补译，但不是待办清单。
  - `upstream_prs`：本次构建**等待中的其他仓库** PR（vllm-plugin-FL /
    FlagGems / FlagTree …），仅为跟踪而记。**已合并的 PR 不写**——它的改动
    已经在所构建的 tag 里，tag 本身就是记录。build-infra 自己的 PR 是交付
    动作本身，不列。

One YAML per image: `base/changelogs/<backend>.yaml` for the base layer,
`runtime/changelogs/<backend>.yaml` for the runtime layer,
`app/<app>/changelogs/<image>.yaml` for the app layer. See each file's header
for the schema:

The filename and the `image:` field inside it are the image name. For the base
and runtime layers the filename is the backend key, as everywhere else that
addresses a backend, and `image:` carries the full image name. For the app
layer the filename is the public name (`{app}{app_version}-{app_name}`, see
`scripts/app_public.py`) — renaming the app layer renames both, and a
**rename is not a rebuild — no new entry**. The workflow's changelog path and
the gate look the file up by that name, so missing one place fails the push.

- `tags`: published tags, newest first. Tags the registry no longer carries are
  folded into the history of the entry that succeeded them — this file is their
  only trace.
- `entries`: one per substantive build, newest first.
  - `date`: the registry `push_time`, normally backfilled by the workflow after
    the push — never hand-typed. The one exception is a retrospectively written
    entry (the base layer's 2.1.2 / 2.2.0 / 2.3.0, whose pushes predate that
    layer having a changelog), where the date is read back from Harbor by hand.
  - `reason`: why this rebuild happened (the change that matters for this
    image). Human-written **markdown**, **one item per bullet**, stating only
    what this version brings — nothing that did not change, no PR numbers, no
    build bookkeeping, no before/after contrast with the previous version (what
    changed follows from what it brings, and does not need saying twice). The
    reason is published alongside the image, so a reason with several items must
    read as a list.
  - `reason_zh`: the same reason in Chinese, with the **same structure** (one
    item per bullet, same count and order). Both languages are published, so a
    new entry carries both; the gate inspects only the pending entry, so a
    missing translation can only be a new one. The 464 entries delivered
    **before the field existed** were translated afterwards — their English
    remains the authoritative text and the Chinese is the same reason in another
    language, not a second reason. More of them can be translated later; it is
    not a to-do list.
  - `upstream_prs`: PENDING PRs in **other** repos (vllm-plugin-FL / FlagGems /
    FlagTree …) that this build is waiting on — a tracking list. A merged PR is
    **not** listed: its change is already in the tag being built, so the tag is
    the record. build-infra PRs are the delivery action itself and are not
    listed.

## 流程 / Flow

1. 人写一条待定条目（reason + reason_zh，`date` 留空）并提交。
2. 触发 push 构建 —— 门禁检查该 tag 是否有待定条目、两种语言是否都非空：
   新 tag 需有 tag 记录，同 tag 重打需在既有 block 下新增待定条目。无则拒。
3. 构建 → 校验 → push。
4. record 步骤回填 `date` = registry `push_time`（app 层与 image_tag 记录同一个 PR）。

1. A human commits a pending entry (reason + reason_zh, empty `date`).
2. Trigger the push build — the gate checks for a pending entry for this tag and
   that both languages are written: a new tag needs a tag record; a re-push
   needs a new pending entry under the existing block. Refuse otherwise.
3. Build → verify → push.
4. The record step backfills `date` = registry `push_time` (the app layer in
   the same PR as its image_tag record).

门禁无需查 registry 或比较时钟：已交付条目的 `date` 一定非空（已回填），
因此"`date` 为空"就等价于"有人准备好了这次重建"。

The gate needs no registry query or clock comparison: a delivered entry is
always dated (backfilled), so an empty `date` unambiguously means a human
prepared this rebuild.

## 发布 / Publishing

每一层镜像的用户可读面都带一节 Changelog：

- **文档站**：镜像页末节 `## Changelog` / `## 更新日志`，最新 tag 在前；
- **Harbor**：仓库描述里的同一节（base/runtime 的 `<layer>/<name>.md`、
  app 的 `app/<组件>/<镜像>.md` 为描述源）。

这一节**从 changelog 文件重算**，不烘进页面本体：页面的其余部分由各自的
生成器按各自的节奏产出（base 页需要版本 TSV，runtime 页在发版收尾时渲染一次），
若一节随整页输出，两条线中后跑的那条会把期间写下的条目抹掉。重算点有三处：
每层的 record 步骤（回填日期之后）、站点构建前、Harbor 上传前
（`gen_descriptions.py --changelog-only`）。因此**读者看到的永远与 main 上的
changelog 一致**，页面上提交的那一节只是缓存，由下一次 record / gendoc 修正。

两条与「读者看什么」有关的规则：

- **待定条目（`date` 为空）不发布** —— 它描述的 push 还没发生，不是读者能拿到的
  变更。回填日期后它才出现，而这正是 record 步骤刷新本节的原因。
- **`upstream_prs` 不发布** —— 它是维护者的跟踪清单，不是这次构建带给用户的变更。

Every layer's user-facing surface carries a Changelog section:

- **Docs site**: the last section of each image page, newest tag first;
- **Harbor**: the same section in the repository description (fed by
  `<layer>/<name>.md` for base/runtime and `app/<component>/<image>.md` for app).

The section is **recomputed from the changelog file**, never baked into a page
body: the rest of a page is produced by its own generator on its own cadence
(the base pages need version TSVs, the runtime pages render once at the end of a
release), and if the section rode along with that output, whichever line ran
last would drop the entries written in between. It is recomputed in three
places — each layer's record step (after the date is backfilled), the site
build, and the Harbor upload (`gen_descriptions.py --changelog-only`). **What a
reader sees therefore always matches the changelog on main**; the copy
committed in the page is a cache that the next record or gendoc run corrects.

Two rules about what a reader sees:

- **A pending entry (empty `date`) is not published** — the push it describes
  has not happened, so it is not a change anyone can have. It appears once the
  date is backfilled, which is exactly why the record step refreshes the
  section.
- **`upstream_prs` is not published** — it is maintainer bookkeeping, not a
  change this build brings.

## 相关 / See also

- 生成式文档与 review 门禁的既有模式：`docs/status-matrix.md`
- 落位：base 层 `.github/workflows/base-image.yml`，runtime 层
  `.github/workflows/runtime-image.yml`，app 层
  `.github/workflows/{vllm,sglang,megatron}-app-image.yml`
  （门禁 → 构建 → push → 回填）。base 层按 2.1.2 / 2.2.0 / 2.3.0 三个 tag
  回溯补写了文件，日期取当时 registry 的 `push_time`；该层自回溯之后的
  push 走本文档描述的流程。
- 门禁：`scripts/changelog_gate.py`；回填：`scripts/backfill_changelog_date.py`；
  记录集成：`scripts/record_image.py`（`--layer base|runtime|app`）。
