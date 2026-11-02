---
name: rollout-app-version
description: >-
  Take a supported application (vllm / sglang / megatron training / rl) to a NEW
  version: the new app key, its status matrix, changelogs, per-version docs,
  launch pages and the verify loop. Trigger on upgrade vllm / new sglang version
  / megatron 0.18.2 / bump an app version / 新版本 app / app 版本升级. NOT for:
  backend build-layer bumps (deps, compiler, SDK, stack version — see
  update-backend), publishing a wheel (see publish-wheel), or walking one
  already-declared cell (see verify-app-backend).
---

# Roll Out an App Version

## Context

An app version is an **app key**: the app's name run together with the version,
no separator (`vllm<ver>`, `megatron_training<ver>`, `megatron_rl<ver>`,
`sglang<ver>`). The key — not the version string — is the unit everything else
hangs off: the `deps_app` entry, the status matrix file, the changelog
filenames, the verify registry, the launch pages. Rolling out a version means
creating that key and then walking it to verified, and the shape is the same
for all four lines.

**Two rules decide the whole rollout:**

- **A new version never inherits the old version's ✅.** The cells start ⬜ and
  are earned on-node, dual-compiler, on the new artifact. Copying the previous
  version's matrix and editing the key is how a matrix comes to claim
  verification that never happened — it was done once already and had to be
  reverted.
- **An app version is not a backend version.** The runtime and base images do
  not move here; only the app layer's wheel and Containerfile arg change. If
  the work is "the compiler/SDK/deps moved", that is `update-backend`.

## Prerequisites

- The upstream release actually exists and its wheel/sdist is published
  (a version that is not released cannot be rolled out, and building from a
  branch head is not a rollout).
- Which packaging model the app uses: **repack** (vllm, sglang — upstream
  sdist, emptied and re-stamped `+flagos`) or **fork-source wheel** (megatron —
  built from the FlagOS fork). The model decides what §2 changes.
- The backend set this version is being admitted to. Admission is the
  `deps_app` key; it does not assert verification.

## Standard flow

### 1. Create the key and admit the backends

Add `deps_app.<appkey>:` per backend in `configs.yaml`. **Key presence is
admission to the build matrix** — a backend without the key neither builds the
app nor gets a launch page. `[]` means "buildable, no vendor package".

Do not add the app's own wheel here: it is the app's identity and rides the
Containerfile's version arg, not per-backend conditionality.

### 2. Change what the packaging model requires

- **repack apps**: the repack rules in `packaging/<app>/config.yaml` — which
  upstream dependencies get removed or pinned — are version-specific and must
  be re-derived for the new upstream metadata, not carried over. This is where
  a bump actually breaks: a dependency the old rules handled by name may now be
  reachable only indirectly.
- **the app Containerfile's version arg** (`VLLM_VERSION`, `SGLANG_VERSION`,
  `MEGATRON_VERSION`) — the one place the version string lives.
- **the wheel line's default** for that app, so the wheel and the image agree.
- **fork-source apps**: nothing in `packaging/<app>/` changes but the docs —
  the version is a workflow input and the Containerfile arg.

Per-line specifics belong to each app's own `DESIGN.md` / per-version
`playbook.md`; read those, don't infer from another app.

### 3. Create the status matrix and its marker block

Copy the schema (not the contents) into `packaging/<component>/status_matrix.<appkey>.yaml`.
Two things are easy to get wrong:

- **every cell ⬜.** A fresh version's matrix that carries ✅ fails the same way
  the copy did.
- **the marker block must exist in the rendered markdown before the renderer
  runs** — `<!-- status-matrix:facility:<appkey> -->` … `<!-- /... -->`. The
  renderer writes only marker interiors and exits when a block is missing, so
  a hand-created matrix without its block renders nothing and says so late.

The renderer discovers matrices by filename, so no registry entry is needed for
a new version of an existing component; a new *component* does need its entry.

### 4. The orchestration registry is a separate gate — and a hole

The cell-collection registry is a hard-coded map keyed by app key. **A new
version is invisible to the orchestrator until it is registered there**, and
nothing fails when it isn't — the app simply never appears in a collected plan.
Register it as part of the rollout, not "when someone notices".

(This is the one place where the rollout is not automatic; treat it as a
required edit, and check the current map's shape in the script before adding.)

### 5. Changelogs, one per image

One changelog file per `(app version × backend public name)` — the filename is
the **public** name, not the backend key. Each image's push is gated on a
**pending** entry (empty date, `reason` **and** `reason_zh`), so the entries
are written before the build, not after. An unpublished combination generates a
`TBD` tag placeholder; nothing needs to be fabricated for it.

### 6. Verify, then record

Walk the cells with `verify-app-backend`: F and T on the same image, on-node,
full E2E. Then the record step writes `image_tag` — **which is what "published"
means** in this repo. Two things the generator will not do for you:

- a retraction (a combo that must go back to unpublished) requires deleting
  the generated page/readme and the changelog, not just clearing the matrix
  field;
- a matrix `image_tag` that was never actually pushed passes every consistency
  check. It is a claim about Harbor, and only you can keep it true.

### 7. Regenerate, in that order

The app pages and readmes are generated from the matrix + the changelog, so the
order is fixed and the last step is not optional:

```
gen_data → gen_descriptions --app-only → gen_descriptions --changelog-only --layer app
```

`--app-only` re-renders whole pages and drops the Changelog section; the
`--changelog-only` pass restores it. Skipping the third command ships pages
missing their Changelog. Both the local pre-commit hook and a CI workflow
enforce this, and they open a fix PR rather than failing loudly — so a green
push is not proof the pages are right.

## Facts index

- App key naming, per-version doc layout, the reference-maintenance list:
  `packaging/README.md`
- Status matrix schema, symbols, `image_tag` semantics: `docs/status-matrix.md`
- Changelog schema and the pending-entry gate: `docs/changelog.md`
- Per-version history, blockers, leftover items, playbooks:
  `packaging/<app>/docs/<app>-<ver>/` (entry: that directory's README)
- Packaging model rationale (repack vs fork): `packaging/<app>/DESIGN.md`
- Cell walk + F/T discipline: `.claude/skills/verify-app-backend/SKILL.md`
- Public naming and why the app layer is vendor-neutral:
  `scripts/app_public.py`, `configs.yaml app_public`
- Stack-wide release flow (a different axis): `docs/release-workbook.md`

## Why these exist

- Cells never inherit: verification is a property of an artifact, and a new
  version is a new artifact. A carried-over ✅ is a false claim that nothing
  downstream can detect.
- Key-presence-is-admission: the build matrix, the launch pages and the docs
  pipeline all derive from one `deps_app` key, so they cannot disagree about
  which backends a version supports.
- The marker block, the registry map and the `--changelog-only` pass are all
  places where the failure is silent. They are called out here because reading
  the scripts would not tell you they were missed.
- Changelog before push: the gate is the only thing standing between "someone
  rebuilt an image" and "someone knows why".

## Done when

- The app key exists in `deps_app`; the backends it admits are the intended set.
- A status matrix exists with all cells ⬜, its marker block renders, and the
  version is registered with the cell collector.
- A changelog exists per image, with a pending bilingual entry at push time.
- Cells walked to F+T-passed on the same image; `image_tag` written by the
  record step; per-version docs carry the results and any leftovers.
- The pages are regenerated in the fixed order, including the Changelog pass.
- `CLAUDE.md`'s workflow table and `packaging/README.md`'s 各 app 变体 table
  reflect the new version if the rollout moved anything they describe.

## Failure modes / escalate

- **A version that is not actually released upstream** → stop; the rollout
  waits. Building from a branch head gives a wheel nobody can reproduce.
- **Repack rules never re-derived for the new upstream metadata** → the wheel
  still builds and installs, then pulls a public torch over the vendor one at
  serve time. Check the new rules against the new metadata before verifying.
- **A cell that fails only on T (or only on F)** → not verified, and not a
  reason to record the passing one. Classify the failure and hand it to the
  debug branch (`verify-app-backend`).
- **A backend admitted to `deps_app` with a device-time problem** → leave its
  cells ⬜ and say so; do not narrow the admission key just to make the matrix
  look consistent, and do not fill the cell from an older image.
- **Page or readme drift after a hand-edit** → re-run the generators in order;
  the fix PR the CI opens is a symptom, not the repair.
