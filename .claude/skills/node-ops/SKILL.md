---
name: node-ops
description: >-
  Node-verification operating disciplines for GPU/NPU backend verification and
  debugging. Use when: ssh-ing into a verify node, driving a persistent debug
  container, reproducing a failed cell, cleaning up stale containers, or judging
  slow-vs-hung. Trigger on verify/repro/debug on a node. NOT for: the cell walk
  itself (see verify-app-backend), editing workflows or scripts (that is plain
  code work), or local-only repo operations (no ssh involved). Vendor-specific
  device facts live in docs/vendors/, not here.
---

# Node Operations

## Context

Verification and debugging happen on remote GPU/NPU nodes reached through SSH
aliases (h20, hw25, metax124, ...). These disciplines are hard-won and
platform-agnostic: every one of them caused a false conclusion or a wasted
loop at least once. Read this skill before the first `ssh` of a session; the
facts (which alias maps to which backend) live in
`scripts/verify-nodes.example.yaml`, and everything that is true of *one*
vendor (device nodes, launcher behaviour, hazards, cold-start magnitudes)
lives in `docs/vendors/<vendor>.md` — referenced, not duplicated here.

## Prerequisites

- SSH aliases configured in `~/.ssh/config` (map in
  `scripts/verify-nodes.example.yaml`, git-ignored copy = `verify-nodes.local.yaml`).
- Permission allowlist for ssh/scp/docker already granted in settings.
- The node's own checkout of build-infra (per-node user/owner differs — see §9),
  kept on latest main.

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
<device-enumeration command>   # see docs/vendors/<vendor>.md, or
                               # `.github/build-config.yml` verify.vendors
```

`docker rm -f` any stale containers from earlier sessions — especially ones
with the same name or holding the same die/card. Stale containers silently
hold devices and produce **fake failures**:

- **"out of memory" / "device busy" / "0 devices visible" → check residual
  containers and orphaned worker processes first, not the image.** The
  per-vendor signature (what the fake failure looks like, which host-side
  probe lies, what the clean baseline is, whether the orphan matches
  `docker ps`) lives in `docs/vendors/<vendor>.md` (section 设备状态危险 or
  平台与设备) — read that before concluding a device fault.
- A container that exited is not necessarily a container that let go. Kill,
  don't pause, and re-check `device_count` afterwards.

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

NPU cold-start JIT is extremely slow — first-request times in the tens of
minutes are normal on several vendors. Three rules:

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
A verification harness with a fixed short client timeout will score a healthy
cold start as a failure; widen it (per-vendor magnitudes in
`docs/vendors/<vendor>.md`).

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

### 7. Probe through `bash`, never a bare binary — the shell decides the environment

**How you exec decides what the process sees.** Two mechanisms make a
non-bash probe lie:

1. **Dual-compiler activation is bash-only for every backend.** The runtime
   (flagtree `/opt/flagtree`, vendor triton `/opt/triton`, neither in
   site-packages) activates the default compiler through
   `BASH_ENV=/etc/bash_env.sh` → sources `/etc/profile.d/*.sh` (zz-flagos.sh
   runs last, auto-`compiler flagtree` when no side dir is on PYTHONPATH). The
   side dir on `PYTHONPATH` is what makes `import triton` and `import flag_gems`
   work. A bare `docker exec <c> python3 -c ...` has no shell → no BASH_ENV →
   empty `PYTHONPATH` → `import triton` fails. A blank `PYTHONPATH` seen from a
   non-bash exec is a **probe artifact, not the image being broken**.
2. **Some vendor SDKs publish their env only to bash consumers** — see
   `docs/vendors/<vendor>.md` (section 容器内环境 or 平台与设备) for which, and
   for what the non-bash failure looks like. There the floor in the image is
   short, so `docker run <img> sh probe.sh` **fails falsely** while
   `bash probe.sh` reflects reality.

Rules:

- **Probe through `bash` (or `bash script.sh`), never a bare `python3`, `sh`,
  or `docker run <img> <binary>`.** This matches every docs launch command —
  they all end in `bash`.
- `compiler` does NOT need explicit sourcing: BASH_ENV already sourced
  zz-flagos.sh; `compiler flagtree >/dev/null` is only needed to *switch*.
- Non-login `bash script.sh` reads BASH_ENV (non-interactive bash does), so a
  script run that way is fine — an `sh`-invoked script is not.
- **A failed import or a missing library path is a rig question before it is a
  wheel/env question.** Re-run the same probe under `bash` before concluding
  anything — a RL/training repro that dies at the flash-attn gate is the classic
  instance (flag_gems can't import triton → `supports_paged_attention()`
  degrades to the flash-attn version gate → an unrelated-looking assert).
- To diagnose an env-class issue, run two probes side by side:
  `docker run $I printenv LD_LIBRARY_PATH` (no shell = floor) vs
  `docker run $I bash -c 'echo $LD_LIBRARY_PATH'` (with the profile scripts =
  full). The difference localizes the mechanism.

### 8. Node disk full → check container json.log first, not images

`docker system df`'s `containers` row counts only the writable layer (same for
`docker ps --size`) — NOT `docker/data-root/containers/<id>/<id>-json.log`. A
full node can therefore show `du` reporting the volume nearly full while
`docker system df` reports a few GB; the gap is all json.log.

Root cause is usually a job that neither failed nor finished: no `log-opts` in
daemon.json (json-file unbounded) plus a stuck orphan container looping on
errors at tens of MB/s for days.

Remedy: `docker rm -f <id>` kills the stuck process AND the whole log in one
command. `truncate -s 0` is temporary — the loop refills it.

Still outstanding: several nodes' daemon.json lacks
`"log-opts": {"max-size": "100m", "max-file": "3"}` — a global change needing
a dockerd restart, not done. When a node fills up again, use this section to
locate it before deleting images. Exact node-by-node numbers and the migration
state are in `docs/runner-disk-migration.md`.

When the fix is "move the data directory to another volume" rather than "kill
the stuck container", follow `docs/runner-disk-migration.md` (Docker
`data-root` alone is not enough — containerd's snapshot root is separate).

### 9. Each node's runner user differs — know it before verifying

Verify scripts must run on a real checkout, and each node's checkout location
and owner differ. Don't reuse the previous node's assumptions. The alias →
backend map is `scripts/verify-nodes.example.yaml` (local copy
`verify-nodes.local.yaml`); who owns the checkout per node is not committed —
ask, or infer it from the checkout's owner rather than from the last node you
worked on.

Two recurring pitfalls: (1) a shared checkout where some subdirectory is
root-owned → any ff/checkout fails `cannot create directory ... Permission
denied` — `chown` back to the runner user; (2) a fresh clone checks out clean
(no existing changes blocking), so when a shared checkout is dirty with someone
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

### 11. A runner restart kills in-flight jobs — not a build failure

A job that ends `cancelled` mid-build, with no code-path difference between it
and a later successful dispatch, is usually a runner-listener restart on the
node, not a build problem. Signature: the cancellation timestamp matches a
`Runner_<ts>.log` filename in `<checkout>/actions-runner/_diag/` to the minute;
the worker log shows `Cancellation/Shutdown message received` then
SIGINT/SIGTERM killing the docker process. Trigger is at the listener side:
`BrokerMessageListener` → `SocketException (125) Operation canceled` /
`The HTTP request timed out after 00:01:40` (node→GitHub channel timeout →
reconnect → restart).

**One-command discriminator (cancelled vs self-failure):** in
`gh api .../actions/runs/<id>/jobs`, the job has `runner_name` set and its
last step `conclusion=success`, while the build step log tail is a normal job
wrap-up (`Cleaning up orphan processes` → `Terminate orphan process:
(docker)`) — i.e. the build process was killed, not failed. Then match the
cancellation minute against `_diag/Runner_*.log` timestamps.

Implication: during slow GitHub periods (a build that clones hundreds of MB
in real time, measured ~1.5 MB/min), a job sits exposed in the restart window;
poll-and-redispatch is correct, but confirm with the discriminator first that
it is not a code problem, and after TWO same-cause cancellations STOP and ask
the user — don't retry indefinitely.

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

- Node↔alias map: `scripts/verify-nodes.example.yaml` (local copy
  `verify-nodes.local.yaml`, git-ignored)
- Vendor platform facts (device nodes, launcher behaviour, hazards, cold-start
  magnitudes): `docs/vendors/<vendor>.md`
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
  separate incidents across three vendors).
- Probing through `bash` is mandatory because the runtime activates its
  compiler, and some vendors publish their SDK env, only to bash consumers —
  a bare exec therefore sees a *different environment* than the one the app
  runs in, and reports it as a defect.
- Runner restarts killing in-flight jobs is a node-side fact, not a build
  fact: the discriminator (§11) exists so a cancelled job is not debugged as
  a code problem.

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
- Anything that looks like an image defect on a non-`bash` probe → re-run
  with `bash` before concluding (see §7).
- A vendor-specific device hazard you cannot clear with `docker rm -f` /
  killing the orphan process → check `docs/vendors/<vendor>.md` (设备状态危险)
  for what recovery actually costs (some need a node-level reset); escalate
  with the device command's output.
- A "hung" serve that is actually just slow → §5; if metrics show no
  increment past a generous deadline, escalate with the numbers.
