---
name: verify-app-backend
description: >-
  Walk one status-matrix cell (app × backend × compiler) to a verified,
  recorded end: collect the pending cell, run the app's verify script on the
  node, F/T dual-compiler discipline, symbol write-back, and failure debug
  handoff. Trigger on verify an app image / a backend cell is ⬜ or red /
  status-matrix cell / dual-compiler / F path / T path. NOT for: node ssh
  mechanics (see node-ops) or writing reports (see reporting).
---

# Verify App Backend

## Context

A status-matrix cell is one (app, backend, compiler) combination — e.g.
`vllm0.24.0 / cambricon-neuware4.7.2 / T`. The verify orchestrator
(`docs/verify-orchestrator.md`) drives these through GH Actions for the
deterministic part; the agent drives the judgment part: running the E2E,
classifying failures, recording. This skill is the operating procedure for
ONE cell, on either side of that boundary.

**Top rule — dual-compiler discipline:** a cell is verified only when BOTH
F (FlagTree) and T (Triton) paths pass on the SAME image. Single-path is not
verification. The exception is narrow: under explicit per-PR device-time
pressure, one PR may submit F-only — but then the report must state "F only",
and T is recorded as debt, never as passed. (A stale record from a different
image/base does not vouch for a new artifact.)

## Prerequisites

- Status matrix YAML (`packaging/<app>/status_matrix.<app>.yaml`) with the
  cell at ⬜ (or ❌ pending re-verify).
- The app's verify script: `packaging/<app>/verify/verify-<app>-backend.sh`.
- Node access (see `node-ops` skill) + the app image or runtime image pulled.
- Upstream PRs the cell depends on must be merged (rule 33: default is to
  wait for merge, not build from PR head).

## Standard flow

### 1. Collect the pending cell

```bash
python scripts/verify_collect_cells.py --app <app>     # emits ⬜ cell matrix
```

Each entry: `{app, backend, compiler(F|T), compiler_path, image,
verify_script, verify_args}`. The compiler column maps F→flagtree (default,
`/flagos`), T→triton (`--compiler triton`). The image is the runtime image
(`flagos-runtime-{vendor}-{backend}:{version}`); the cell's app image tag
comes from the matrix `image_tag`.

### 2. Run the verify script (one cell × one compiler)

```bash
packaging/<app>/verify/verify-<app>-backend.sh <backend> \
  --app-image <tag> --compiler <flagtree|triton> <verify_args>
```

Run it ON the node from a refreshed checkout (see `node-ops` §6 — refresh to
main first, never staging). Full E2E mode, not snapshot: the script must
return exit 0 on a real workload (vllm serve returning a true completion;
megatron training mock-data `pretrain_gpt` 5-iter exit 0). Before the serve,
clean residual containers (node-ops §2).

### 3. Dual-compiler discipline

Run the F and T paths on the same image. Between paths, clear the flag_gems
tuning db so the current compiler tunes fresh:

```bash
rm -f /root/.flaggems/config_cache/TunedConfig_*.db   # or FLAGGEMS_DB_URL per compiler
```

Both ✅ → the cell is verified. Record each path's launch mode + compiler
confirmation + result.

### 4. Record the result

- Pass: the symbol goes ✅ in the matrix; the build side
  (`verify_dispatch_build.py`) triggers the app-image build, and
  `record_app_image_tag.py` writes `image_tag` on push.
- Fail: write a structured result (failure step, exit_code, error_head/tail,
  log_path — `verify_record_results.py` appends the task card to
  `.github/verify-queue.yaml` for the debug-loop). The result is ~10 lines,
  not a prose report (verify-orchestrator §5.3).
- The record PR path: `verify_open_pr.py` renders + commits + opens the
  review-gated PR. Main session owns the write.

### 5. Failure → debug branch

A red cell goes to the debug-loop: classify root cause —

- **Local fix** (configs.yaml / Containerfile / verify script) → draft PR in
  build-infra.
- **Upstream bug** (plugin / FlagTree / FlagGems / app core) → draft PR in the
  upstream repo (vllm-plugin-FL / FlagGems / Megatron-LM-FL / verl-FL ...),
  register the full URL in `prs:` when OPEN.
- **No conclusion** → ❌ + note, terminal.

Reproduction mechanics live in `node-ops` (persistent container, stepwise
exec, metrics-increment judgment). Debug-loop worker contract: `claude -p`
on the task card only — never the whole repo.

## Facts index

- Cell schema / symbols / prs registration: `docs/status-matrix.md`
- Orchestrator + worker contract: `docs/verify-orchestrator.md` §4-5
- Node mechanics: `.claude/skills/node-ops/SKILL.md`
- Per-backend history/blockers: `packaging/<app>/docs/<app>-<ver>/backends/<vendor>.md`
- Scripts: `scripts/verify_{collect_cells,record_results,open_pr,dispatch_build}.py`,
  `scripts/verify-debug-loop`, `scripts/verify-nodes.example.yaml`

## Why these exist

- Dual-compiler: two compiler paths are separate code paths with separate
  kernels; a cell passing one proves nothing about the other. The matrix
  encodes this structurally (T/F columns per cell).
- Full-E2E-not-snapshot: "install + import passes" is not "the workload runs";
  the verify script must run the real workload for ✅.
- Structured results: the debug-loop and record PR consume JSON, not prose —
  context stays bounded (orchestrator §5).
- Never re-litigate: a fixed/closed conclusion stays terminal until the
  dependency that blocked it changes (then the cell returns to ⬜).

## Done when

- F and T both exit 0 on the same image; cells ✅; `image_tag` recorded on
  push.
- Or: failure classified, root cause named, draft PR opened (local or
  upstream), `prs:` registered with full URL, symbol ⛔/❌ + note.
- Records written by the main session per agent-protocol.

## Failure modes / escalate

- A "hung" serve — judge slow vs hung by metrics increment first (node-ops §5);
  escalate with numbers only after a generous deadline.
- Upstream PR the cell depends on is still OPEN and the build cannot proceed
  → cell ⛔ with the PR URL; do NOT build from an unmerged head without the
  user's explicit go (rule 33).
- A second device-time pressure request for an F-only exemption → the narrow
  exception exists, but say clearly it is a per-PR debt, never a pass.
- After two same-cause infra cancellations (runner restarts) → stop and ask
  (node-ops §11).
