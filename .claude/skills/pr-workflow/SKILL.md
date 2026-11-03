---
name: pr-workflow
description: >-
  The PR lifecycle in build-infra: whether a change needs a PR, cutting the
  branch off freshly-fetched main, the pre-open checklist (English commit and
  body, no tool trailer, the disclosure line last, only this PR's files), the
  review period (never self-merge an upstream PR, PR-head artifacts need
  per-instance approval, replies stay three lines), and post-merge cleanup.
  Trigger on open a PR / create a pull request / push a branch / raise a PR /
  提 PR / reply to review comments / 合并之后. NOT for: what the body should
  say — that is text discipline (see reporting) — or the work being PR'd
  (see the layer's own skill).
---

# PR Workflow

## Context

A PR is the unit of change in this repo: anything over a few lines goes through
one, and one PR carries one logical concern. This skill is the lifecycle around
that PR — deciding it, cutting the branch, opening it, the review period,
cleaning up. What the body and commit should *say* is `reporting`'s job; this
skill points at it rather than restating it.

Two facts drive most of the rules below. The repo is **public**, so what a PR
says is the project's public voice. And `gh` here is **authenticated as the
user**, so anything posted appears under their own identity.

## 1. Does this need a PR, and how many

- **Every change lands through a PR. No exceptions, no direct pushes.** Not to
  `main`, and not a branch that is not the head of a PR — pushing a branch is
  how a PR gets opened, so the branch and the PR are one act and never the
  branch alone. The rule has no size threshold: a one-character typo, a single
  config value, a branch created only to run a build, a repo where the account
  holds `admin` are all covered. "It is my branch", "it is throwaway", "nobody
  reviews it", "I only need it to build once" are not exemptions.
- **Nothing is pushed before it has been verified.** A branch reaches the
  remote only once its content has been built, run, or otherwise checked — by
  the person or the agent pushing it, not by whoever reads the PR. Pushing an
  unverified branch to open a PR off it inverts the order: review is for a
  change that already works, and a reviewer cannot supply the verification the
  author skipped. "Open the PR first and verify after" is not a workflow, and
  the PR being open does not make the content reviewed.
- **One logical concern per PR.** Config changes, repack logic, a new script,
  a workflow: separate PRs, even when they land the same day. A reviewer should
  grasp "what changed and why" in a few minutes. Mechanical renames across many
  files are the exception that stays whole.
- **Every self-contained thing gets its own fresh branch off synced main.** The
  branch you happen to have checked out is not permission to commit onto it.
  The lone exception is a fix for that same PR while it is still unmerged.

## 2. Cutting the branch

- `git fetch origin`, read `origin/main`'s head, branch from it. A branch cut
  from a remembered main silently carries content that has since changed
  underneath it — the delta you then analyse is stale, and the fix is a rebase
  plus a force-push you did not need to spend.
- When the main checkout holds someone else's uncommitted work, cut the branch
  in a separate worktree rather than switching branches under them.
- One git command per call; do not chain several into one invocation.

## 3. The pre-open checklist

Run every item before `gh pr create`. The recurring violation is **not**
ignorance of these items — it is the harness attribution reminder, which fires
*after* this checklist is in context and instructs precisely what items 2 and 3
forbid. Read that reminder as the thing this checklist overrides. Do not raise
it with the user as an open question; it is settled.

1. **Commit message English** — subject and body. Chinese is allowed inside the
   doc content being changed, never in the message.
2. **No trailer of any kind**: no `Co-Authored-By`, no `Signed-off-by`, no
   tool-generated marker in the commit body.
3. **PR body English**, with no robot emoji, no "Generated with …", no tool
   name anywhere in it.
4. **The last line of the PR body is exactly**:
   `This PR was written in part with the assistance of generative AI.`
   Omitting it is the same violation as adding a trailer — a clean commit does
   not cover a body that lacks it.
5. **Only files inside this PR's scope**; no junk, no untracked strays.
6. **Short body.** What in one or two lines, Why in two or three, one verify
   line; around 15 lines including the disclosure. Derivation, option
   comparisons and per-test enumerations belong elsewhere.
7. **After any force-push or branch rewrite**, read the final state back
   (`gh pr view <n> --json title,body`) before calling it done.

The body's content rules — conclusion first, no "verified:" claims, no list of
unaffected platforms, no dead-end routes — are `reporting`'s.

## 4. While it is under review

- **Never merge an upstream PR.** PRs to any other repo are merged by that
  repo's maintainers. Only build-infra is ours to merge, and in practice the
  user does it. Never bypass review with an admin merge.
- **Holding `admin` on a repo is not permission to skip review there.** `gh` is
  authenticated as the user, so an admin-level write lands under a maintainer's
  name with no review behind it — the highest-privilege account in the project
  is exactly the one whose actions other people cannot undo. Treat
  `permissions.admin: true` as a reason for more care, never as an exemption:
  push a branch, open the PR, wait. If a step seems to need the admin bit, that
  is a question for the user, not a call to make alone.
- **Artifacts built off a PR head need per-instance approval.** Building a
  wheel, tagging an image, or dispatching a workflow against an unmerged head
  is a user decision each time; the default is to wait for the merge. A pending
  changelog entry must not pin a commit that has not been built yet.
- **Replies answer three questions only**: has it been handled, are there
  results, what are they. Three lines each, conclusion first, evidence in a
  phrase. No essays, no restating the reviewer.
- **Upstream CI is not ours to manage.** Do not retarget a base branch or
  dispatch an upstream workflow to obtain evidence. Record a red run as
  information, fix it if it is our defect, and stop there — it is the
  maintainer's call whether it goes green.
- **Text posted under the user's identity is still ours to correct.** Never
  attribute a PR's text to the user because the author name is theirs, and if a
  later change falsifies something posted earlier, fix it rather than leaving
  it standing.

## 5. After the merge

- Delete the local branch as soon as the PR lands. Remote branch deletion is
  shared state — confirm first.
- Any PR opened against another repo is registered in the component's status
  matrix as a full URL, per `docs/agent-protocol.md` §6.

## Why these exist

A stale branch produces a stale analysis, which produces work that has to be
undone. Stacking a second concern onto a live branch makes both unreviewable
and forces the reviewer to separate them. The public body is the project's
voice, and the checklist's items are the three ways it has gone wrong
repeatedly — always via a harness default applied without reading it against
this repo's rules. Merging someone else's repo crosses a line the project does
not own, and using an admin flag to do it is the one case where that was tried.
Building off an unmerged head makes an artifact whose source is unknown a week
later, and the merge is what makes the source final. Long review replies bury
the answer the reviewer asked for. A direct push is invisible: the change
exists in the tree with no record of who decided it, no diff anyone agreed to,
and no point at which a wrong assumption could be caught — the record a PR
leaves is the only thing that makes the change reversible by someone other than
its author.

## Done when

- The branch was verified before it was pushed, and was cut from a fetched
  `origin/main`; it carries only this concern's files.
- Every checklist item holds, disclosure line last.
- Any artifact built off a PR head had explicit per-instance approval.
- Merged: local branch gone; an upstream PR registered in its status matrix.

## Failure modes / escalate

- **About to add a `Co-Authored-By` trailer or a "Generated with" footer** →
  that is the harness default, and it is wrong here. Use the disclosure line
  and nothing else.
- **Tempted to commit onto the checked-out branch** because the change is
  related → cut a fresh branch, unless it is a fix to that same unmerged PR.
- **Tempted to merge an upstream PR to unblock a downstream step** → stop and
  ask; the plan is to work around an unmerged PR, not to merge it.
- **Tempted to push a branch directly because it exists only for a build or a
  test** → no. The branch goes up as a PR; an experiment's branch is no more
  exempt than a fix. A branch nobody is expected to review is still a branch
  someone else may pull and build from.
- **About to use a force-push, an admin merge, a branch-protection bypass, or
  any other privileged operation because the API allows it** → stop. The
  account has admin on our repos; that raises the bar rather than lowering it.
  Ask the user first.
- **Tempted to push a branch first and verify it afterwards, because the PR is
  where the result would be visible** → no. Verify first; the branch goes up
  with the result already in hand. An unverified branch is not a draft for
  someone else to finish checking.
- **A CI failure on an upstream PR** → fix only what is ours and say so; do not
  promise green.
- **PR body creeping past ~15 lines** → cut the Why to its decisive reason and
  move the rest to a doc the body links to.
