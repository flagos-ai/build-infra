---
name: reporting
description: >-
  Report-writing and chat-reply discipline for docs, PR bodies, commit bodies,
  and conversation replies. Use when: writing or editing any markdown report
  (packaging/*/docs, base/runtime pages), a PR description or commit message,
  or replying in chat about work done. Trigger on write a report / summarize /
  PR body / commit message. NOT for: code comments (their own 3-line rule), or
  writing code.
---

# Reporting

## Context

These rules make reports usable by the next person who needs to get a thing
done — not a diary of what was done. Every report answers one question: is
this reproducible for the reader, or informative for another platform's
testing? If neither, it does not belong. The same discipline constrains PR
bodies, commit messages, AND chat replies (rule 12/13 below).

## Rules

### Structure & tables

1. **No long text in table cells.** If a cell would hold prose, use numbered
   or bulleted lists instead. Tables are for comparison and listing where
   cells are SHORT values (versions, dates, statuses, names). Criterion is
   cell length, not scenario type.
2. **Wrap at ~150 English chars / ~75-80 full-width Chinese chars** per line
   (long URLs, code blocks, table rows exempt).
3. **Never break between two CJK characters** — the newline renders as a
   visible space in HTML. Break only at punctuation (，。；：) or CJK/English
   boundaries. When checking "no break between CJK", look at the FIRST
   non-blank char of the continuation line (a list indent starts with spaces,
   so checking `[0]` misses it).

### Content

4. **Minimal, no repetition.** A fact appears once; later references point to
   it (link/section number). Cut redundant modifiers and restated narratives.
5. **Every real defect named in a report carries a disposition** — a fix, or
   an explicit todo. A defect without one leaves the reader unsure who does
   what next.
6. **Dates/times in UTC+8** (`2026-08-17 11:36`), never "UTC 03:36" arithmetic.
7. **No ephemeral identifiers** in final reports: container names, temp script
   names, login node names, run numbers/counts ("10 runs" vs "20 runs" carries
   no reproducible difference). Record the reproducible content: commands,
   parameters, versions, findings, dispositions.
8. **No dead-end routes.** Missteps with no value are omitted entirely. A
   valuable attempt that did not succeed may be recorded briefly (background,
   failure point, why abandoned).
9. **Latest facts, not timeline.** Write the current correct state: problem →
   disposition → resolved-or-not. No "X 日前提前提已过时" narratives.
10. **Conclusion-oriented.** Keep only what helps the reader reproduce or
    what informs another platform. Intermediate artifacts (a temp wheel built
    in a container) are not recorded; the final reproducible path is:
    source → artifact → verification.

### Chat & PR/commit bodies

11. **Metadata label lines (`**标签:** 值`) need a blank line between them** —
    without it HTML merges them into one paragraph and it becomes unreadable
    (report headers stacking 日期/平台/镜像/... ). Each line its own paragraph,
    or use a list/table. Judge by whether HTML would merge them.
12. **The brevity rules constrain chat replies and PR/commit bodies too.**
    Answer the direct question directly — no background, no option
    comparisons, no self-corrections ("顺带修正我上一轮的说法"). Answer first;
    offer detail only if asked. A yes/no or count answer is ≤5 lines. PR/commit
    bodies carry only point conclusions, not derivation.
13. **Delete what doesn't change the conclusion**, two classes: (a) values/
    branches that don't hold (a failed cell whose exclusion doesn't change the
    conclusion — e.g. an env value's unset branch); (b) failure counts and
    detours before success — the final recipe is one; the n failures along the
    way have no reproduction value. Stronger than "write less": delete it,
    don't keep it as background.

### Language

- Plain, jargon-free technical language. Give the full form of an abbreviation
  at first use (THD, TE, MLF). No invented terms.

## Why these exist

Long text in table cells renders as unreadable single lines. Jargon loses
readers outside the immediate team. Repetition breeds inconsistency when one
copy is edited. Defects without dispositions are records, not executable
conclusions. Ephemeral identifiers look like part of the recipe to the next
reader. Dead-end routes are pure noise; valuable failures help others avoid
the same pit. Timeline narratives mean something only to the writer. A
report without reproducible path gives the reader no way forward. Merged
label lines are unreadable. Long replies and PR bodies bury the conclusion.
Unheld values and pre-success failures mislead more than they inform.

## Done when

- Every table cell holds a short value; long content is in lists.
- Lines wrap at punctuation / CJK-EN boundaries; no CJK-CJK breaks.
- Every defect carries a disposition.
- No container/temp names or run counts.
- Chat/PR/commit bodies are conclusion-first and short.

## Failure modes / escalate

- Writing a history of what happened this session → rewrite as the current
  correct state.
- Tempted to enumerate platforms NOT affected → drop them; name only the
  affected path.
- Tempted to mention a failed value/branch that doesn't change the conclusion
  → delete it (rule 13).
