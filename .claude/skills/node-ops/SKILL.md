---
name: node-ops
description: >-
  Node-verification operating disciplines for GPU/NPU backend verification and
  debugging. Use when: ssh-ing into a verify node (h20/hw25/metax124/...),
  driving a persistent debug container, reproducing a failed cell, cleaning up
  stale containers, or judging slow-vs-hung. Trigger on verify/repro/debug on
  a node. NOT for: editing workflows or scripts (that is plain code work), or
  local-only repo operations (no ssh involved).
---

# Node Operations

## Context

Verification and debugging happen on remote GPU/NPU nodes reached through SSH
aliases (h20, hw25, metax124, ...). These disciplines are hard-won and
platform-agnostic: every one of them caused a false conclusion or a wasted
loop at least once. Read this skill before the first `ssh` of a session; the
facts (which alias maps to which backend, what the node's checkout looks like)
live in `scripts/verify-nodes.example.yaml` and the per-version
`packaging/<app>/docs/` backends records — referenced, not duplicated here.

## Prerequisites

- SSH aliases configured in `~/.ssh/config` (map in
  `scripts/verify-nodes.example.yaml`, git-ignored copy = `verify-nodes.local.yaml`).
- Permission allowlist for ssh/scp/docker already granted in settings.
- The node's own checkout of build-infra (per-node user/owner differs — see
  §4), kept on latest main.

## Standard flow

### 1. Debug mode = persistent container + stepwise `docker exec`

Do NOT iterate via "edit workflow → push → trigger → read logs" (minutes per
iteration, no visibility into where it hangs). Instead:

```bash
# start once, container lives until the job is done
ssh h20 "docker rm -f <name> 2>/dev/null; docker run -d --name <name> --gpus all \
  --entrypoint sleep -e http_proxy=... -e https_proxy=... \
  -v /host/repo:/container/repo:ro <image> infinity"
# one logical step per exec — short, clear, fails fast
ssh h20 "docker exec <name> bash -c '...single command...'"
```

- One exec = one logical step; do not chain 10 commands.
- Set proxy with `-e` at container start; `unset` inside exec when hitting
  domestic services.
- Protect a writable working copy with `cp -a` before changing it.

### 2. Clean residual containers before any verify serve

**Hard rule.** Before starting any verification serve, list running containers
and check the device is free:

```bash
docker ps
cnmon   # or nvidia-smi / npu-smi info / hy-smi / mx-smi per vendor
```

`docker rm -f` any stale containers from earlier sessions — especially ones
with the same name or holding the same die/card. Stale containers silently
hold devices and produce **fake failures**:

- cambricon: `Free memory ... < 0.6 utilization` despite a healthy image.
- ascend: dies occupied → `npu-smi` HBM well above baseline (~3.4GB/die idle
  for 910B4); host `npu-smi` never tells you a container holds a die.
- **"out of memory" / "device busy" → check residual containers first, not
  the image.** On ascend, `path string is NULL` / `DrvMngGetConsoleLogLevel
  failed (ret=4)` / `dcmi -8020` also spam PASSING job logs — not failure
  signals; the only real gate is `torch.npu.device_count()`.

Also mandatory: verification serve containers must mount
`-v /data/models:/data/models:ro`. Missing it yields `HFValidationError: Repo
id must be ...` — huggingface_hub validates the local path as a repo id, and
the error does NOT point at the real cause.

### 3. Files to the node = `scp` to `/tmp`

`scp <localfile> <node>:` lands in `/tmp/<basename>` no matter what target
path you write; then `docker cp /tmp/foo.tar.gz <container>:<path>`. Never
pipe large base64 over ssh stdin (JumpServer truncates; ~4K cut on a 700K
payload). Quoted remote inline commands get their single quotes hex-escaped
(0x27) — write complex scripts locally → scp → docker cp → exec the file, and
keep inline quoting out of it.

### 4. After triggering a workflow: notification = action signal

Do not end a turn with "waiting" and leave progress-watching to the user. The
task notification (build done/failed) is the hard trigger: act on it and move
to the next step. Really waiting = wait for the notification only; when it
arrives, move.

### 5. Slow vs hung: judge by metrics increment, not client timeout

NPU cold-start JIT is extremely slow (hw25 T 872s, hw26 F longer). Three rules:

- **Client timeout ≠ server failure.** `curl -m N` expiring only means this
  side gave up; the server may still be working. First step after a timeout =
  check the server's real state, not "hung".
- Distinguish slow/hung on ONE signal: is `vllm:generation_tokens_total`
  growing, and does `num_requests_running` drop to zero? Counter moving = slow,
  not hung. Grab it within 30s of the first timeout, not after a ten-minute round.
- Find the right filesystem: a curl running inside `docker exec` writes the
  **container's** `/tmp`, not the host's. Look for results in the container,
  or have curl stream to stdout instead of a file.

Correct posture for long requests: background curl (no short timeout) + active
polling of metrics increments — not a foreground fixed-timeout retry loop.

### 6. Node verify = refresh the repo checkout first, never "grab anything"

**Hard rule.** Node verification runs from the node's build-infra checkout on
**latest main**, never a staging copy in /tmp (the old sed-SCRIPT_DIR +
/tmp/configs.yaml pattern) and never silently trusting a possibly stale
configs.yaml. The "grab anything" pattern has recurred (a wheel built from
2.1.2, the node repo still on 2.1.1, verify pulling the wrong image).

Refresh (github goes through the runner systemd unit's proxy; don't echo the
value):

```bash
eval "$(systemctl cat 'actions.runner.*' | sed -n 's/^Environment="\([^"]*\)"/export \1/p')"
git fetch origin && git merge --ff-only origin/main
```

- Local WIP on the node → stash first, then ff (keep the stash, don't delete).
- The verify scripts (`verify-megatron-backend.sh`, `verify-vllm-backend.sh`)
  resolve the repo root by FIXED relative path — no walk-up search — so a
  /tmp staging resolves to a directory without configs.yaml and fails LOUDLY
  instead of silently grabbing another configs.yaml.
- Header prints `Stack Version: X.Y.Z (path/configs.yaml (discovered) |
  --stack-version (explicit))` — read this line before running. If the node
  repo is stale and you don't want to refresh, pin with
  `--stack-version <ver>`.

### 7. Ascend: use `bash` for probes inside containers, never `sh`

`base/ascend-*` images publish the full CANN env ONLY to bash consumers: the
build sources CANN's `set_env.sh` into `/etc/profile.d/vendor.sh` and sets
`ENV BASH_ENV=/etc/bash_env.sh` so `bash -c` auto-reads it. The hand-written
`ENV LD_LIBRARY_PATH` is a short floor missing the driver dirs — `sh`/dash,
`docker run <img> <binary>` (no shell) and systemd get that floor, and
`libascend_dump/ml/trace` fails to find `libascend_hal.so`.

Consequence: **`docker run <img> sh /path/probe.sh` fails falsely;
`bash /path/probe.sh` reflects reality.** A FlagCX .deb was misjudged as
defective for exactly this reason (the .deb was fine; the harness used `sh`).

The short floor is FINAL — do not propose fixing `base/ascend-*`. Bash is the
standard call (all docs' launch commands end in `bash`); rebuilding all 20
images (4 base + 4 runtime + 12 app, plus per-backend re-verification) buys
only dev/non-bash convenience.

To diagnose LD_LIBRARY_PATH-class issues, run two probes side by side:
`docker run $I printenv LD_LIBRARY_PATH` (no shell = floor) vs
`docker run $I bash -c 'echo $LD_LIBRARY_PATH'` (with vendor.sh = full).

### 7b. BASH_ENV + `compiler`: bash-only, and *how* you exec decides everything

The dual-compiler runtime (flagtree `/opt/flagtree`, vendor triton `/opt/triton`,
neither in site-packages) activates its default compiler through
`BASH_ENV=/etc/bash_env.sh` → sources `/etc/profile.d/*.sh` (zz-compiler.sh
runs last, auto-`compiler flagtree` when no side dir is on PYTHONPATH). The
compiler side dir is what makes `import triton` and `import flag_gems` work —
flag_gems *requires* triton, and `supports_paged_attention()` degrades to the
flash-attn version gate (assert fires, RL dies at `attention.py:1105`) when
flag_gems can't import triton. This bit me as a *false negative* on a metax
RL repro: I probed with `docker exec <c> python3 -c ...` (no shell = NO
BASH_ENV → empty PYTHONPATH → `import triton` fails → asserted it was a
wheel/env bug). Same container, `docker exec <c> bash -c '...'` or
`bash /script.sh` → BASH_ENV applies → triton/flag_gems import fine → RL E2E
passes. Rules:

- **Probe through `bash` (or a `bash script.sh`), never a bare `python3`/
  `sh`/`docker run <img> <binary>`** — that is the "vllm way" and it also
  matches every docs launch command (they all end in `bash`).
- `compiler` does NOT need explicit sourcing: BASH_ENV already sourced
  zz-compiler.sh; `compiler flagtree >/dev/null` is only needed to *switch*.
  A blank `PYTHONPATH` seen from a non-bash exec is a probe artifact, not the
  image being broken.
- Corollary: a RL/training repro that hangs at the flash-attn gate is
  *first* an exec-rig question (bash vs not), *before* suspecting the wheel.
  Non-login `bash script.sh` reads BASH_ENV (non-interactive bash does), so a
  script run that way is fine — but an `sh`-invoked script is not.

### 8. Node disk full → check container json.log first, not images

`docker system df`'s `containers` row counts only the writable layer (same for
`docker ps --size`) — NOT `/data/docker/containers/<id>/<id>-json.log`. So a
full node can show `du` saying 24T while `docker system df` says 16GB — the
gap is all json.log. Images and build cache are usually irrelevant at that
scale (metax124: images 470G + build cache 212G vs one log 26T).

Root cause was a job that neither failed nor finished: no `log-opts` in
daemon.json (json-file unbounded), a stuck orphan container's process looping
on errors at ~39MB/s for 5 days.

Remedy: `docker rm -f <id>` kills the stuck process AND the whole log in one
command (26T log vs 4.0T after). `truncate -s 0` is temporary — the loop
refills it.

Still outstanding: metax124 (and other nodes) daemon.json lacks
`"log-opts": {"max-size": "100m", "max-file": "3"}` — a global change needing
a dockerd restart, not done. When a node fills up again, use this section to
locate it before deleting images.

### 9. Each node's runner user differs — know it before verifying

Verify scripts must run on a real checkout, and each node's checkout location
and owner differ. Don't reuse the previous node's assumptions. Canonical
example map (per-node): kunlunxin `secure` at `/home/secure/build-infra`;
ix15 `tengqm` (not secure) at `/home/tengqm/build-infra`; h20 `secure` at
`/home/secure/build-infra` (general-purpose test node — Ubuntu 24.04, git
2.43, python3.12 with `packaging`, docker 29.1.3, proxy already in env;
best place for hardware-independent script/git experiments).

Two ix15 pitfalls: (1) a shared checkout where `app/sglang` was root-owned →
any ff/checkout fails `cannot create directory ... Permission denied` —
`chown` back to the runner user; (2) a fresh clone checks out clean (no
existing changes blocking), so when a shared checkout is dirty with someone
else's WIP, clone a second copy into your own verify dir and delete it after.

### 10. SSH: non-pty exec channels are dead; pty sessions are the usable command channel

**Conclusion first:** the bastion REJECTS non-pty session requests, but
pty-capable interactive sessions work fully — spawn processes, `docker exec`,
real remote side effects. A prior round misread this as "only sftp remains"
and outsourced the whole job to the user — the pty channel can drive the node
itself.

**One-command discriminator:** `ssh -T <node> 'id'` fails LOUDLY (not
silently): `ssh: rejected: connect failed (open failed)` — the bastion
refuses to open a session channel for the non-pty request. rc stays 0, so
reading only rc misjudges it as "ran, no output".

Same failure family (all "on-demand non-pty channels"): `ssh host '<cmd>'`
silently side-effect-free; `rsync` over ssh → `unexpected end of file`; legacy
`scp -O` → `lost connection`; `ssh -L` forward → reset right after connect
(curl exit 56 / http_code 000). **Verdict: on-demand spawn channels all dead,
pty interactive sessions all alive.** Not a local-env issue (`env -i`,
`RequestTTY=force`, `ControlMaster=no` all ineffective; no
ProxyCommand/ForceCommand/RemoteCommand in `~/.ssh/config`; same repro on
other bastion targets) → the fault is at the bastion policy layer, stop
re-investigating your own side.

**Usable recipe** (the `/tmp/node_run.sh` skeleton):

```bash
{ sleep 4; printf '%s\n' "$CMD"; sleep "$WAIT"; printf 'echo __NODE_DONE__\n'; sleep 3; printf 'exit\n'; } \
  | timeout 600 ssh -tt -o ConnectTimeout=25 -o BatchMode=yes <node> 2>&1
```

All three sleeps are required, not insurance: 4s lets the login shell come up
(early input is eaten by session init); WAIT must exceed the commanded
command's runtime (the pty tears down the session the moment it reads `exit`,
taking still-running output with it); 3s lets the sentinel and tail flush.
Make WAIT a parameter, default generous (e.g. 20s).

Costs and boundaries: a backend process can still escape the pty with
`setsid nohup … < /dev/null &`. sftp moves files but cannot reach the
container FS (overlay; only shared path is a bind mount — but writes don't
trigger execution, don't treat it as deliver-and-run). `docker exec` with `-d`
starts background; `-i` is needed to receive stdin (without `-i` a heredoc is
dropped, which looks exactly like "no result" — easy misjudgment).

**WAIT shorter than the commanded command = the child dies too** (worse than
dropping output): the pty sends HUP/INT to the whole session group on `exit`,
killing the driving script itself. Long commands (multi-round clone / build /
serve start) MUST go through `setsid nohup bash x.sh > log 2>&1 </dev/null &`
as a detached session process, polled with a short pty session; don't try to
out-wait it with a bigger WAIT. Also: a local pipe feeding `sed -n '/start/,/end/p'`
buffers the whole run — the log file stays 0 bytes during the run, looking
like "nothing ran" — don't wrap polling in a range sed.

### 11. CANN-node runner restart kills in-flight jobs — not a build failure

`flagtree-wheel.yml`'s `ascend-cann8.5.0` had two consecutive `upload=true`
builds (114 / 147 min) end `cancelled` — not a build or workflow problem:
both cancellation timestamps (13:26, 16:27) match the runner listener's
restart times on hw26 **minute-for-minute** — `Runner_<ts>.log` filenames in
`/home/secure/actions-runner/_diag/` timestamped seconds after the
cancellations, worker log same-minute `Cancellation/Shutdown message
received`, then SIGINT/SIGTERM killing the docker process. Trigger is at the
listener side: `BrokerMessageListener` → `SocketException (125) Operation
canceled` / `The HTTP request timed out after 00:01:40` (node→GitHub channel
timeout → reconnect → restart). A third dispatch 22 min later succeeded with
no code-path difference.

**One-command discriminator (cancelled vs self-failure):** in
`gh api .../actions/runs/<id>/jobs`, the job has `runner_name` set and its
last step `conclusion=success`, while the build step log tail is a normal job
wrap-up (`Cleaning up orphan processes` → `Terminate orphan process:
(docker)`) — i.e. the build process was killed, not failed. Then match the
cancellation minute against `_diag/Runner_*.log` timestamps.

Implication: during slow GitHub periods (AscendNPU-IR builds clone hundreds
of MB in real time, measured ~1.5 MB/min), a job sits exposed in the restart
window; poll-and-redispatch is correct, but confirm with the discriminator
first that it is not a code problem, and after TWO same-cause cancellations
STOP and ask the user — don't retry indefinitely.

### 12. Feeding scripts over ssh + wait loops: four traps

For multi-step scripts on the node, `ssh <node> 'bash -s' <<'OUTER' … OUTER`
is handiest, but:

- **`ssh -n <node> 'bash -s' <<'EOF'` silently does NOTHING**: `-n` points
  remote stdin at /dev/null, the heredoc is dropped entirely — no output, no
  error. Drop `-n` when feeding a script; use `-n` only for a single command.
- **Nested heredoc terminators must differ** (outer `OUTER`, inner `IN`). With
  the same name the outer script is truncated at the inner terminator and the
  tail executes as commands — again "no output", easy to misjudge as a node
  problem.
- **In a wait loop, `pgrep -f "<script> --backend X"` matches the waiting
  process itself** (the remote `bash -lc` cmdline contains the string), the
  loop never exits, and an ssh channel is held forever. Break the self-match
  with `pgrep -f "<script[.]sh>"`.
- **A local `timeout` shorter than the remote command kills the remote too**
  (node `git fetch` via proxy routinely exceeds 120s). Split long actions
  into separate ssh calls: one for fetch/checkout only, one to start
  `nohup … &` and sleep a few seconds to peek at the first lines.

## Facts index

- Node↔alias map, per-node checkout owner: `scripts/verify-nodes.example.yaml`
- Verify script conventions + task-card contract: `docs/verify-orchestrator.md` §5
- Status-matrix symbol semantics: `docs/status-matrix.md`
- F/T dual-compiler discipline: `verify-app-backend` skill (top rule)
- Per-backend history/blockers: `packaging/<app>/docs/<app>-<ver>/backends/<vendor>.md`

## Why these exist

- Persistent-container + stepwise exec beats workflow-iteration loops because a
  workflow run is minute-granular and hides the hang point; exec is second-granular
  and fails fast. (First verified 2026-07-26: 3 workflow failures + 10 min
  monitoring vs 30 min to find and fix 9 problems.)
- Cleaning residual containers is mandatory because stale containers hold
  devices and produce fake failures that read as image defects (three
  separate incidents; the quantitative rule is the HBM baseline).
- `bash`-not-`sh` on ascend is a documented FINAL decision: the short floor is
  kept, bash is standard, and 20-image rebuild was judged not worth it for
  non-bash convenience. Do not re-litigate.

## Done when

- Every step of a verify run is driven via persistent container + stepwise exec.
- No stale containers/devices left; the serve ran on a clean board.
- Files land in `/tmp` via scp; no base64-over-stdin.
- Slow/hung judged by metrics increments with results in the right filesystem.
- The node checkout was refreshed to main (or tag pinned explicitly).
- Results/records written per agent-protocol (main session owns writes).
- Leftover temp containers/images/scripts cleaned up (work-rules rule 12).

## Failure modes / escalate

- Two same-cause runner-restart cancellations → stop, ask the user.
- A node's disk genuinely full and `log-opts` still unset → it is a
  pre-existing global gap; report with exact numbers, do not delete images.
- Anything that looks like an ascend image defect on a `sh`-run probe → re-run
  with `bash` before concluding (see §7).
- A "hung" serve that is actually just slow → §5; if metrics show no
  increment past a generous deadline, escalate with the numbers.
