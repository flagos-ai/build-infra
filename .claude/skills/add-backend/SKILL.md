---
name: add-backend
description: >-
  Add a new vendor or backend to the build-infra stack: base Containerfile,
  configs.yaml vendors entry, runner override, matrix smoke test, status-matrix
  declaration, and the runtime/app verification loop. Trigger on add a new
  backend / new vendor / 新增后端 / spacemit container / iluvatar upgrade.
  NOT for: changing an existing backend's deps or env (plain config work), or
  verify debugging of a failing cell (see verify-app-backend).
---

# Add a Backend

## Context

A backend is `{vendor}-{backend}` (e.g. `nvidia-cuda12.8`, `ascend-cann9.0.0`,
`spacemit-spacemit`). Adding one touches every layer of the stack: the base
image, the runtime build matrix, the status matrix, and (optionally) the app
layer. `configs.yaml` is the single source of truth; `build-config.yml` owns
runners + device flags. A new VENDOR additionally needs `app_public`, `run`,
and `verify.vendors` entries. This flow replaces the 4-line sketch in
CLAUDE.md "Adding a new backend", which misses the runtime/matrix/status/app
steps.

## Prerequisites

- A vendor SDK + toolchain that installs on Ubuntu 24.04 (the base layer).
- Device access facts: how the node's runner is labeled, what `docker run`
  flags expose the accelerator (see §5 if unknown).
- Write permission via PR (never push main directly).

## Standard flow

### 1. Base image

Create `base/<vendor>-<backend>` (Containerfile) — the name MUST match the
`{vendor}-{backend}` key. Model it on the nearest existing vendor
(`base/nvidia-*` for CUDA-family, `base/ascend-*` for CANN, etc.). The file
installs the vendor SDK/toolchain on Ubuntu 24.04 and sets `ENV`
(PATH/LD_LIBRARY_PATH) exactly as the image ends up.

### 2. configs.yaml — the backend spec

Under `vendors.<vendor>.<backend>`, add the full spec. Fields (see the
configs.yaml header comment for the authoritative contract):

| Field | Meaning |
|---|---|
| `extras` | FlagGems pyproject extra name, passed as `EXTRAS_GROUP` |
| `hardware` / `driver` / `sdk` | display metadata (driver is the floor, not the shipped version) |
| `python` | venv Python version |
| `cmake_backend` | FLAGGEMS_BACKEND for C++ extensions (only where supported) |
| `triton` / `flagtree` | compiler package pins (FlagTree is default, Triton side-installed to `/opt/triton`) |
| `deps` | explicit Python deps for the runtime venv (no extras — unreliable across vendor indexes) |
| `deps_app` | per-app vendor-conditional packages, keyed `{app}{version}`; KEY PRESENCE = admitted to that app's build matrix |
| `env` | `base`/`runtime`/`app` env split — must mirror EXACTLY what the images set (rule 34: audit downstream consumers in the same PR) |

A new vendor also needs an `app_public` entry (`scripts/app_public.py`
resolves the app-layer public name from it; `drop: [cuda]` etc.).

### 3. build-config.yml — runner + device flags

- `runners.overrides.<backend>`: the runner label (arch or GPU-specific;
  default `[self-hosted, h20]`).
- `run.vendors.<vendor>`: device-passthrough flags for `docker run`
  (`toolkit`, `raw`, or `toolkit_cmd`), plus `prereq` (container toolkit).
- `verify.vendors.<vendor>`: the device-enumeration command (nvidia-smi /
  npu-smi info / cnmon / ...).

### 4. Matrix smoke test

```bash
python scripts/generate_matrix.py <backend>        # builds + emits matrix JSON
python scripts/build_base.py <backend> --dry-run   # base image preview
python scripts/build_runtime.py <backend> --dry-run
```

The backend key must flow through `generate_matrix.py` unchanged; a mismatch
here is a silent no-row (see §5 `fromjson` trap).

### 5. Status matrix + docs

- Declare the backend in `packaging/<app>/status_matrix.<app>.yaml`
  (`scenarios.<sid>.verification.<backend>: {T, F}`) — a backend has a row
  only where the app line is opened on it. Add the backend key to
  `scripts/render_status_matrix.py` `BACKENDS` (display order is fixed there).
- `deps_app` key presence gates the app build matrix; verification symbols
  (✅/❌/⛔) are separate and come from the verify loop (see
  `verify-app-backend` skill).
- Regenerate data/docs: `python docs/gen_data.py` → `docs/data/images.yaml`
  (gen_data reads `build-config.yml` run flags + configs.yaml env). Update
  `base/<name>.md`/launch pages via the gendoc workflows — generated, not
  hand-written.
- If the backend needs an SSH entry for verification: add the alias to
  `scripts/verify-nodes.example.yaml` + the local
  `scripts/verify-nodes.local.yaml`.

### 6. Runtime + app verification loop

1. Build + push base and runtime images (manual `trigger.yml` / `runtime.yml`,
   or `scripts/build_*.py`).
2. Verify the runtime: F (flagtree) + T (triton) dual-compiler E2E both ✅ —
   see the `verify-app-backend` skill.
3. Only then mark the status-matrix cells and record `image_tag`.

## Facts index

- Backend spec contract + env split: `configs.yaml` header comment
- Runners/device flags/verify commands: `.github/build-config.yml`
- Status-matrix schema + symbols: `docs/status-matrix.md`
- Verify-cell flow: `.claude/skills/verify-app-backend/SKILL.md`
- Image naming: CLAUDE.md "Image naming"
- Docs data flow: `docs/gen_data.py`, `docs/gen_descriptions.py`

## Why these exist

- configs.yaml is single source of truth so builds, docs, and matrices can
  never disagree; the backend key is the join column across all of them.
- Device flags live in build-config.yml because they are per-node facts
  (driver layout), not image content; they gate both the verify scripts and
  the launch docs.
- The status matrix declares a backend only where an app line opens on it —
  an unopened backend has no row, `—` means "no compiler", not "not here".
- FlagTree is the default compiler; Triton is a side install because it is
  the fallback path (both verified per the dual-compiler discipline).

## Done when

- `generate_matrix.py <backend>` emits the row with the right runner.
- `build_base.py --dry-run` / `build_runtime.py --dry-run` resolve cleanly.
- Status matrix declares the backend; BACKENDS list includes it.
- F/T dual-path verification passed on-node and symbols are written back.
- Published images carry `image_tag` in the matrix.

## Failure modes / escalate

- **Device flags unknown** (new vendor): do NOT guess — check whether an
  existing vendor's `raw` matches the device layout, confirm the node's
  toolkit presence (`run.vendors.prereq`), and if still unsure, ask the user
  for the launch flags before building. The launch docs inherit these flags.
- **Runner labels wrong → job queues forever**: `generate_matrix.py` emits
  `runson` as a JSON string; the workflow must `fromjson` it before feeding
  `runs-on`. A `[self-hosted, xxx]` label with no registered runner silently
  never schedules. Check the label against the runner list first.
- **A backend key that cannot map through `app_public.py`** (a public name
  fed back into the backend whitelist): app-layer names must never round-trip
  into `name.split("-", 1)` or the BACKENDS whitelist.

## Checklist

- [ ] `base/<vendor>-<backend>` Containerfile exists and builds
- [ ] configs.yaml `vendors.<vendor>.<backend>` complete (deps/env/deps_app/
      compilers) + env mirrors Containerfile ENV
- [ ] `app_public` (new vendor), `runners.overrides`, `run.vendors`,
      `verify.vendors` in build-config.yml
- [ ] `generate_matrix.py <backend>` → correct row + runner
- [ ] BACKENDS + status-matrix declaration added
- [ ] verify-nodes alias (example + local)
- [ ] base/runtime images built + pushed; F/T verified on-node
- [ ] cells ✅ / image_tag recorded; docs regenerated
