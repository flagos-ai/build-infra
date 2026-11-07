---
name: add-backend
description: >-
  Stand up a brand-new backend (a new vendor SDK line) across the base →
  runtime → app layers: pick the permanent backend key, write its base
  Containerfile + configs block + build-config entries, gate each layer's push
  on a pending changelog, and verify-first / record-after, one PR per layer.
  Trigger on add a new backend / 新增后端 / 新 vendor / new SDK line / stand up
  <vendor>-<backend>. NOT for: bumping an existing backend's deps/compiler/SDK
  or the stack version (see update-backend), taking an app to a new version
  (see rollout-app-version), or publishing a component wheel (see
  publish-wheel). Vendor device facts live in docs/vendors/, not here.
---

# Add a New Backend

## Context

Adding a backend is rare and front-loaded: it is the add-tail of
`update-backend` (it shares every rebuild / verify / record step) plus a set
of net-new declarations that nothing else in the repo creates for you. Two
facts shape the whole job.

**The backend key is permanent.** It names the base-image SDK line
(`<vendor>-<backend>`, e.g. the clang/SDK version the base reports) and every
layer addresses the backend by it: the runner label, the Containerfile name,
`--backend`, the status-matrix key, the changelog filenames, the verify-node
alias. Picking it is step zero, because renaming it later is not an edit — it
strands the key in a dozen files that must all be swept in lockstep (see
"Replace, don't strand"). A vendor that ships more than one SDK line gets one
key per line (as ascend keeps cann8.5.0 / cann9.0.0 side by side); the key is
the SDK line, not the vendor.

**Verify-first, record-after, layer by layer.** base ← runtime ← app is a
build chain, and each layer is its own PR gated on its own pending changelog.
A cell stays ⬜ until on-node dual-compiler verification passes; an image is
not "added" because its Containerfile exists, only once it is built, pushed and
verified. Do not open the app layer before an image exists to put under it.

## Prerequisites

- The `configs.yaml` backend-spec contract (its header comment) and
  `docs/changelog.md` (the pending-entry gate).
- A decided backend key (the SDK line it names).
- A base-image source: either a vendor SDK installable on Ubuntu 24.04, or —
  when the vendor only ships the SDK inside their own image — a vendored
  `FROM` that image (drop its entrypoint, repoint pip; this is a legitimate
  pattern, not a shortcut).
- Device-launch flags for the vendor. **For a NEW vendor these are unknown —
  ask the user before building; the launch docs inherit them.**
- Real wheels already on the vendor index (`flagos-pypi-<vendor>`), never a
  direct vendor URL — see `publish-wheel`.
- F/T node access for the verify loop (see `node-ops`, `verify-app-backend`).

## Standard flow

The layers below are an ordered plan — work them in order and let each layer
decide when the next opens; a grep of the new key does not re-order them.

### 1. base layer (its own PR)

- `base/<vendor>-<backend>` Containerfile — install the vendor SDK on Ubuntu
  24.04, or vendor the vendor's image. Comments say *why*, matched to the
  code's density (the recurring miss is a comment block several times the size
  of the lines it covers).
- `configs.yaml` `vendors.<vendor>.<backend>` block (deps / env / compilers /
  sdk; `app_public` for a NEW vendor — `scripts/app_public.py` reads it, and
  the public name must never round-trip into the backend key).
- `.github/build-config.yml`: `runners.overrides.<backend>`,
  `run.vendors.<vendor>` device flags, `verify.vendors.<vendor>` smi command.
  Write only the launch tiers the vendor actually has — an empty or duplicated
  `toolkit:` the vendor lacks is noise; drop it with its comment.
- `base/changelogs/<backend>.yaml` — a pending entry (`reason` + `reason_zh`,
  **empty date**); `scripts/changelog_gate.py` gates the push and the layer's
  workflow backfills the date. Do not hand-type a date.
- PR → merge → dispatch Build Base Image (`.github/workflows/base-image.yml`,
  `push=true`) on the backend's runner; the gendoc / pubdoc workflows then
  produce the description page. Triggering the workflow needs membership in
  `.github/builders.txt`.

### 2. runtime layer (its own PR)

`runtime/changelogs/<backend>.yaml` pending entry; the runtime build reads the
`configs.yaml` deps / compilers already landed in step 1, and the description
comes from the gendoc workflow — do not hand-generate it.

### 3. app layer (its own PR)

`deps_app` (+ `env.app`) in `configs.yaml` and the app Containerfile; the
`status_matrix.<app>.yaml` declaration; then the verify loop
(`verify-app-backend`). A backend with no `deps_app` is not app-buildable yet
and its matrix row stays `deps_app: false` — declare it so, do not pretend a
cell.

### 4. Matrix + node wiring (fold into the layer that needs it)

`scripts/generate_matrix.py` row, the `BACKENDS` list in
`scripts/render_status_matrix.py`, the `scripts/verify-debug-loop` alias map,
and `scripts/verify-nodes.example.yaml` + a local alias for the node.

## Replace, don't strand

The backend key lives in many places. If you ever rename it, drop it, or
discover a placeholder key that was never real, sweep ALL of them in one PR so
no dangling key remains: `configs.yaml`, the `base/` Containerfile +
`base/changelogs/`, `runtime/changelogs/`, `.github/build-config.yml`,
`scripts/generate_matrix.py`, every `packaging/<app>/status_matrix.*.yaml`,
the `BACKENDS` list in `scripts/render_status_matrix.py`,
`scripts/verify-debug-loop`, `scripts/verify-nodes.example.yaml`, and the app
docs — then re-run `scripts/render_status_matrix.py` and commit its regenerated
matrices. One exception: a published-wheel record in `packaging/packages.yaml`
names a real artifact on the index; changing it is a publish decision, not a
rename — leave it and raise it.

## Facts index

- Backend spec contract + env split: `configs.yaml` header comment
- Runner / device / verify: `.github/build-config.yml`
- The backend's own record (vendored-image story, node quirks, index wheels):
  `docs/vendors/<vendor>.md`
- Shared update / rebuild / verify / record mechanics: the `update-backend`
  skill
- Publish gate: `scripts/changelog_gate.py` + `docs/changelog.md`
- Per-layer PR discipline + the disclosure line: `pr-workflow`
- App-cell verify: `verify-app-backend`; node mechanics: `node-ops`
- Real wheels on the vendor index: `publish-wheel`

## Why these exist

- The key is load-bearing across layers, so picking it precisely once is
  cheaper than a repo-wide sweep later — a stranded key breaks the
  status-matrix consistency check and queues nothing on a label no runner has.
- Layer-by-layer PRs keep each change reviewable and let the build chain decide
  the rebuild set; a cell that goes ✅ before on-node verification is a claim
  the image cannot back.
- The pending-changelog gate is what authorizes every image push; a hand-typed
  date reads as "already delivered" and the gate rejects the push.
- A vendored base image is the only path when the vendor ships the SDK solely
  inside an image — refusing it would mean no backend at all.

## Done when

- The backend key is decided once and used verbatim everywhere it is addressed.
- Each layer landed as its own PR, gated on a pending (empty-date) changelog in
  both languages; the image was built, pushed and verified before any cell
  went ✅.
- Device flags for a new vendor were confirmed with the user, not guessed.
- No dangling key anywhere (consistency check green); any published-wheel
  record left to a publish decision was raised, not silently rewritten.

## Failure modes / escalate

- **New vendor, device flags unknown** → ask the user before building; the
  launch docs and `build-config.yml` inherit whatever you write.
- **Runner label with no runner** queues the job forever — confirm the runner
  (org-level runners do not show in the repo's runner list; absence there is
  not absence of a runner).
- **A base build that fails on the runner environment** is a node-provisioning
  gap, not a repo defect — report and fix it on the node, do not retry the
  same-cause failure blindly (`node-ops`). The one seen so far: a
  docker-socket `permission denied`. A process's supplementary groups are
  fixed at start, so adding the runner's user to the `docker` group does not
  reach the already-running runner — restart it from a fresh login (check
  `/proc/<pid>/status` Groups). On an ephemeral VM, bake the membership in
  before the runner autostarts, or it recurs on every rebuild.
- **Tempted to open the app layer before an image exists** → steps 1–3 are a
  first delivery; 4 opens only once there is an image to declare or a node to
  verify on.
