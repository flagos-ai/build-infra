---
name: update-backend
description: >-
  Update or upgrade a backend's build config: bump deps / compiler (flagtree,
  triton) / SDK / python / version for one backend or across many backends,
  including the flat-tag stack version bump. Trigger on update a backend /
  upgrade flagtree / bump flag_gems / upgrade torch / change deps / stack
  version bump / 升级. Also covers the RARE add-a-new-backend flow. NOT for:
  app-line version upgrades (vllm 0.24.0, megatron 0.18.2 — those have their
  own per-version docs), or verifying a failing cell (see verify-app-backend).
---

# Update / Upgrade a Backend

## Context

Updating a backend is the repo's most frequent agent operation. The shape is
always the same: change a pinned version (compiler, torch, flag_gems, SDK,
python) → audit downstream consumers → rebuild → re-verify → record. The flat
tag means a rebuild OVERWRITES the same tag, so "is the pushed image stale"
and "who must rebuild" are the two questions that gate everything. The rebuild
set is decided by the layer chain — base ← runtime ← app (§1) — not by the
calendar: a compiler or flag_gems bump is a runtime-layer change however it
arrives. configs.yaml is the single source of truth; a change there never
travels alone (rule 34: audit downstream in the same PR).

Adding a brand-new backend is the rare tail of the same flow — it shares the
spec/verify/record steps; only the first two sections differ.

## Prerequisites

- The configs.yaml backend spec contract (header comment).
- Decided scope: one backend, a cross-backend compiler bump, or the stack
  version bump (see §1).
- F/T verification access on the affected node (see `verify-app-backend` +
  `node-ops` skills).

## Standard flow

### 1. Classify the change (propagation scope)

Classify by **what the change touches**, never by when it happens: a compiler
or flag_gems bump is a runtime-layer change whether it arrives in a release
test window, as routine maintenance, or as an emergency upgrade mid-cycle.
Every change has its own impact scope — there is no "default" set of images.

The scope follows the build chain, base ← runtime ← app:

- `runtime/Containerfile` does `FROM ${BASE_IMAGE}` — a runtime image **is** a
  base image plus a wheel-installed venv. Any base change (SDK package,
  `env.base`, base Containerfile, python) may change what the runtime builds
  on and therefore needs the runtime **and every app on it** rebuilt +
  re-verified.
- app Containerfiles do `FROM ${RUNTIME_IMAGE}` — any runtime change (deps,
  compiler, flag_gems, venv) is baked into every app image on that runtime,
  so all of them must rebuild + re-verify.
- Only a change that stops above the runtime (app Containerfile, `deps_app`,
  `env.app`) is app-scoped and leaves base + runtime untouched.

| Change touches | rebuild set | re-verify |
|---|---|---|
| base layer (SDK, `env.base`, base Containerfile, python) | base + runtime + all apps on it | F/T on the rebuilt runtime; app cells reopen (§4) |
| runtime layer (deps, compiler, flag_gems, `env.runtime`) | runtime + all apps on it (base unchanged) | F/T on rebuilt runtime; app cells reopen |
| app layer (`deps_app`, `env.app`, app Containerfile) | the app images only | that app's cells (its runtime is untouched) |
| stack `version:` bump | **ALL backends** — every image rebuilt to carry the new tag | whole matrix, backend by backend |

The stack version is what a release ships, and it lives as the flat tag on
every image. Two contexts see the same truth, differently paced:

- **During a release window** the bump is the opening act: the release version
  is picked once, then each backend goes through base → runtime → app for that
  version; after 定版, the whole repo gets a `vX.Y.Z` git tag and a release
  branch for maintenance.
- **Between releases** the same number is just the target version in
  configs.yaml — and the moment it changes, the full stack (nearly every
  image) must be rebuilt layer by layer, backend by backend, because the flat
  tag would otherwise lie: only some backends carrying the new tag is a broken
  publish.

In both cases the rule is identical: the version changed ⇒ the whole stack
rebuilds. Timing changes only the rhythm, never the scope.

Flat-tag semantics: base and runtime share the flat `X.Y.Z` tag; a rebuilt
image overwrites it. Which pushed images are behind HEAD is answered by
`scripts/base_image_status.py` (reads `revision`/`version` OCI labels off
Harbor, diffs since that commit) — run it before a selective rebuild to know
the actual build set, don't guess from git alone. **It only answers base
staleness**: there is no runtime/app stale checker, so downstream rebuilds are
traced manually along the FROM chain above — ask "which runtime is on this
base, which apps are on that runtime" for every changed pin.

### 2. Apply the config change

Edit the pinned versions in `configs.yaml`. A version bump to a vendor package
(compiler / torch / flag_gems / SDK) needs the version's actual content
verified before it is committed — a new flagtree/flag_gems version is a real
dependency change, not a text edit.

**Same-PR downstream audit (rule 34, non-negotiable):** any configs.yaml
change MUST check, in the same PR:

- `env` change → the Containerfile ENV it documents and every consumer
  (`docs/gen_data.py` → images.yaml → gen_descriptions pages; the build-args
  path in `scripts/build_runtime.py`).
- `deps` / compiler pin change → does the runtime build arg derive from it
  (`DEPS`, `FLAGTREE_PKG`, `TRITON_PKG`, `CPP_EXTRA`)?
- A package version appearing in the flagcx/flagtree wheel pins (the wheel
  family reads configs.yaml too).
- The app layer (`deps_app` / `env.app`) — only if the change reaches it.

Two definitions that look alike and are NOT: `driver:` is the FLOOR, not the
installed version (never "fix" it to match a node); a base Containerfile ENV
and configs.yaml `env.base` must mirror EXACTLY (the one is the image reality,
the other its documentation source).

### 3. Rebuild + push

```bash
python scripts/build_base.py <backend> --dry-run
python scripts/build_runtime.py <backend> --dry-run     # resolve build args
python scripts/generate_matrix.py <backend>             # row + runner intact
```

Then the manual workflows (`base-image.yaml` base / `runtime-image.yaml`
runtime). When the changed image is a rebuilt wheel with the SAME version as
one already pushed, pass the no-cache path (`runtime-image.yaml no_cache=true`
— forces a fresh download of a pre/daily wheel with an identical name; the
version-CHANGED case rebuilds automatically, no cache flag needed). Flat tag
overwrite is the intended publication model — a rebuilt image replaces the old
tag. Scope of the rebuild is §1's propagation set: a base or runtime change
does not stop at the image you edited — its dependents go through this same
build+push+verify cycle.

### 4. Verify (dual-compiler, same image)

Rebuilt image → old verification records do NOT vouch for it. Re-verify F and
T on the new image before anything records success (`verify-app-backend`).
This includes the propagation case: a base or runtime rebuild changes the
artifact beneath every app on it, so those app cells return to ⬜ and re-verify
on the new runtime — the stale records were taken on a different image.
Between paths, clear the flag_gems tuning db (fresh tuning under the current
compiler).

### 5. Publish gate + record

- `changelog_gate.py <changelog> <tag>` — a pending (empty-date) entry must
  exist before the push is authorized; the app-image workflows backfill the
  date on push. A rebuilt tag with a changed commit needs a NEW pending entry
  under the same tag block. The gate exists only in the app-image workflows
  today — base and runtime pushes have no changelog gate yet (a known gap,
  not a design choice). App-image pushes gate on both changelog and the
  on-node verify step.
- On verified push: `record_app_image_tag.py` writes `image_tag` into the
  status matrix (published ⟺ image_tag present).
- The status matrix cells move ⬜ → ✅ only after on-node dual-compiler
  verification; a base/runtime change reopens every app cell built on the
  changed image (§1 propagation, §4 note).

### 6. Docs (generated, not hand-written)

`docs/gen_data.py` → images.yaml → `gen_descriptions.py` (base/runtime pages).
The gendoc workflows extract the versions from the built images and open a
review-gated PR; package version bumps surface there. Don't hand-edit
`base/*.md` / `runtime/*.md`.

## Add a new backend (rare)

Follow `update-backend` for the shared steps, with these additions up front:

1. `base/<vendor>-<backend>` Containerfile (new vendor SDK on Ubuntu 24.04).
2. configs.yaml `vendors.<vendor>.<backend>` full spec (deps/env/deps_app/
   compilers) + `app_public` for a NEW vendor (`scripts/app_public.py` reads
   it; the public name must never round-trip into the backend key).
3. `build-config.yml`: `runners.overrides.<backend>`, `run.vendors.<vendor>`
   (device flags), `verify.vendors.<vendor>` (smi command).
4. Matrix + status matrix: `generate_matrix.py` row, `BACKENDS` list,
   `status_matrix.<app>.yaml` declaration. **Device flags unknown (new
   vendor) → ask the user before building; launch docs inherit these flags.**
5. `verify-nodes.example.yaml` + local alias for the node.

## Facts index

- Backend spec contract + env split: `configs.yaml` header comment
- Stale-image answer: `scripts/base_image_status.py` (OCI labels vs Containerfile)
- Publish gate: `scripts/changelog_gate.py` + `docs/changelog.md` (app-image
  workflows only — base/runtime not yet gated)
- Record: `scripts/record_app_image_tag.py` + `docs/status-matrix.md`
- Verify-cell flow: `.claude/skills/verify-app-backend/SKILL.md`
- Node mechanics: `.claude/skills/node-ops/SKILL.md`
- Runners/device flags: `.github/build-config.yml`
- App-line version upgrades: `packaging/<app>/docs/<app>-<ver>/` (their own
  four-piece docs — NOT this skill)

## Why these exist

- The flat tag makes stale detection a real question, so `base_image_status.py`
  exists and must be run, not eyeballed from git.
- Rebuilds overwrite the same tag by design — "is it stale" is answered by
  labels+diff, never by tag uniqueness.
- The layer chain decides the rebuild set: base ← runtime ← app, and a change
  anywhere below an image propagates up through everything built on it. There
  is no runtime/app stale checker, so the trace is manual — but the FROM chain
  makes it deterministic.
- A config change is never a one-file edit: every consumer of the changed
  value (build args, docs pipeline, wheel pins) must be audited in the same
  PR, or two definitions drift (rule 34, PR #633 evidence).
- Old records don't vouch for new images: a rebuild changes what the artifact
  is, so dual-compiler verification restarts from ⬜ — including the app cells
  sitting on a rebuilt runtime.
- The stack version names the release; its change re-tags nearly the whole
  stack, so it is the widest-scope edit in the repo no matter when it lands.

## Done when

- configs.yaml change + downstream audit in the same PR (rule 34).
- Rebuild set decided by `base_image_status.py`, not guesswork.
- Rebuilt images re-verified F/T on-node; cells ✅.
- Pending changelog entry authorized the push (app-image pushes; base/runtime
  have no gate yet — trace the rebuild without one); `image_tag` recorded.
- Docs regenerated through the gendoc PR, not hand-edited.

## Failure modes / escalate

- **"Redundant" or "stale" claims without a query first** (rule 4's trap):
  before proposing to delete/merge a config field, run the query that decides
  it (`git tag --contains <sha>`, `git log -S`, grep current tree). A value
  that looks redundant may be a compatibility patch for an old-tag build path.
- **A new compiler/flag_gems version whose behavior is unverified**: bumping
  the pin is not the work — verifying the new wheel on-node is. Don't commit
  a pin you haven't seen run (the no_cache rule: same-version rebuild needs
  no_cache=true; version change auto-rebuilds).
- **Runner label wrong → job queues forever**: `runson` is a JSON string; the
  workflow must `fromjson` it before `runs-on` (a label with no runner
  silently never schedules).
- **Stack version bump without full rebuild**: the flat tag lies if only some
  backends carry it — every backend must be rebuilt to the new version tag,
  layer by layer (base → runtime → app), whatever the timing.
- Two same-cause runner-restart cancellations → stop and ask (node-ops §11).

## Checklist

- [ ] Scope classified by what the change touches (base / runtime / app /
      stack version), not by when it happened
- [ ] Rebuild set traced along the FROM chain: everything on the changed
      layer re-enters build+verify
- [ ] configs.yaml edit + same-PR downstream audit (env/containerfile, build
      args, wheel pins, app layer as touched)
- [ ] `base_image_status.py` → actual rebuild set (base staleness; runtime/app
      traced manually)
- [ ] base/runtime rebuilt + pushed (no_cache=true only for same-version
      rebuild of an identical-named wheel)
- [ ] F/T re-verified on the new image; affected app cells reopened and
      re-verified; cells updated
- [ ] changelog pending entry gated the push (app-image pushes only; base/
      runtime pushes have no gate — verify their rebuild by trace); `image_tag`
      recorded
- [ ] gendoc PR refreshed the generated pages (no hand-edits)
