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
（reason，date 留空）。push 前门禁检查该条目是否存在；没有就拒绝 push。
调试构建（`push=false`）不受此限。

**An image is never rebuilt without a documented reason.** Before a rebuild, a
pending entry (reason, empty date) must be added to the changelog. A push-time
gate refuses the push when it is absent. Debug builds (`push=false`) are exempt.

## 文件与结构 / Files and schema

逐镜像一个文件，分 app 放在 `app/<app>/changelogs/<image>.yaml`
（base/runtime 层同理，落位待定）。字段含义见文件头注释：

- `tags`：发布过的 tag，按时间**倒序**（最新在前）。已被替换、registry 不再
  保留的 tag 折叠进取代它的那条 entry 的历史叙述里——本文件是它唯一的痕迹。
- `entries`：每次实质构建一条，按时间**倒序**。
  - `date`：registry 的 `push_time`，由工作流在 push 后回填，**不手写**。
  - `reason`：本次重建的理由（对该镜像有意义的变更）。人写。
  - `upstream_prs`：本次构建引入的**其他仓库** PR（vllm-plugin-FL /
    FlagGems / FlagTree …）。build-infra 自己的 PR 是交付动作本身，不列。

One YAML per image under `app/<app>/changelogs/<image>.yaml` (base/runtime
follow the same idea; placement TBD). See each file's header for the schema:

- `tags`: published tags, newest first. Tags the registry no longer carries are
  folded into the history of the entry that succeeded them — this file is their
  only trace.
- `entries`: one per substantive build, newest first.
  - `date`: the registry `push_time`, backfilled by the workflow after the
    push — never hand-typed.
  - `reason`: why this rebuild happened (the change that matters for this
    image). Human-written.
  - `upstream_prs`: PRs in **other** repos incorporated by this build.
    build-infra PRs are the delivery action itself and are not listed.

## 流程 / Flow

1. 人写一条待定条目（reason，`date` 留空）并提交。
2. 触发 push 构建 —— 门禁检查该 tag 是否有待定条目：新 tag 需有 tag 记录，
   同 tag 重打需在既有 block 下新增待定条目。无则拒。
3. 构建 → 校验 → push。
4. record 步骤回填 `date` = registry `push_time`，与 image_tag 记录同一个 PR。

1. A human commits a pending entry (reason, empty `date`).
2. Trigger the push build — the gate checks for a pending entry for this tag:
   a new tag needs a tag record; a re-push needs a new pending entry under the
   existing block. Refuse otherwise.
3. Build → verify → push.
4. The record step backfills `date` = registry `push_time`, in the same PR as
   the image_tag record.

门禁无需查 registry 或比较时钟：已交付条目的 `date` 一定非空（已回填），
因此"`date` 为空"就等价于"有人准备好了这次重建"。

The gate needs no registry query or clock comparison: a delivered entry is
always dated (backfilled), so an empty `date` unambiguously means a human
prepared this rebuild.

## 相关 / See also

- 生成式文档与 review 门禁的既有模式：`docs/status-matrix.md`
- 门禁：`scripts/changelog_gate.py`；回填：`scripts/backfill_changelog_date.py`；
  记录集成：`scripts/record_app_image_tag.py`。
