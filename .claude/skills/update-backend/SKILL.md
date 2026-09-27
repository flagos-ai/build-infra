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
and "who must rebuild" are the two questions that gate everything. configs.yaml
is the single source of truth; a change there never travels alone (rule 34:
audit downstream in the same PR).

Adding a brand-new backend is the rare tail of the same flow — it shares the
spec/verify/record steps; only the first two sections differ.

## Prerequisites

- The configs.yaml backend spec contract (header comment).
- Decided scope: one backend, a cross-backend compiler bump, or the stack
  version bump (see §1).
- F/T verification access on the affected node (see `verify-app-backend` +
  `node-ops` skills).

## Standard flow

### 1. Classify the change (scope matrix)

| Change | touches | rebuild set |
|---|---|---|
| one backend `deps:` / `triton` / `flagtree` / `python` / `env` | that `vendors.<v>.<b>` block | that backend's base+runtime (app if `deps_app`/`env.app` changed) |
| cross-backend compiler bump (flagtree 0.7.0, flag_gems version) | N `vendors` blocks | all N backends (base unchanged unless SDK/deps moved) |
| stack `version:` bump | one line in configs.yaml | ALL backends — every image must be rebuilt to carry the new tag |

Flat-tag semantics: base and runtime share the flat `X.Y.Z` tag; a rebuilt
image overwrites it. Which pushed images are behind HEAD is answered by
`scripts/base_image_status.py` (reads `revision`/`version` OCI labels off
Harbor, diffs since that commit) — run it before a selective rebuild to know
the actual build set, don't guess from git alone.

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

Then the manual workflows (`trigger.yml` base / `runtime.yml` runtime). When
the changed image is a rebuilt wheel with the SAME version as one already
pushed, pass the no-cache path (`runtime.yml no_cache=true` — forces a fresh
download of a pre/daily wheel with an identical name; the version-CHANGED
case rebuilds automatically, no cache flag needed). Flat tag overwrite is the
intended publication model — a rebuilt image replaces the old tag.

### 4. Verify (dual-compiler, same image)

Rebuilt image → old verification records do NOT vouch for it. Re-verify F and
T on the new image before anything records success (`verify-app-backend`).
Between paths, clear the flag_gems tuning db (fresh tuning under the current
compiler).

### 5. Publish gate + record

- `changelog_gate.py <changelog> <tag>` — a pending (empty-date) entry must
  exist before the push is authorized; the app-image workflow backfills the
  date on push. A rebuilt tag with a changed commit needs a NEW pending entry
  under the same tag block.
- On verified push: `record_app_image_tag.py` writes `image_tag` into the
  status matrix (published ⟺ image_tag present).
- The status matrix cells move ⬜ → ✅ only after on-node dual-compiler
  verification; cross-backend bumps touch every affected backend's cells.

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
- Publish gate: `scripts/changelog_gate.py` + `docs/changelog.md`
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
- A config change is never a one-file edit: every consumer of the changed
  value (build args, docs pipeline, wheel pins) must be audited in the same
  PR, or two definitions drift (rule 34, PR #633 evidence).
- Old records don't vouch for new images: a rebuild changes what the artifact
  is, so dual-compiler verification restarts from ⬜.

## Done when

- configs.yaml change + downstream audit in the same PR (rule 34).
- Rebuild set decided by `base_image_status.py`, not guesswork.
- Rebuilt images re-verified F/T on-node; cells ✅.
- Pending changelog entry authorized the push; `image_tag` recorded.
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
  backends carry it — every backend must be rebuilt to the new version tag.
- Two same-cause runner-restart cancellations → stop and ask (node-ops §11).

## Checklist

- [ ] Scope classified (single / cross-backend / stack version)
- [ ] configs.yaml edit + same-PR downstream audit (env/containerfile, build
      args, wheel pins, app layer as touched)
- [ ] `base_image_status.py` → actual rebuild set
- [ ] base/runtime rebuilt + pushed (no_cache=true only for same-version
      rebuild of an identical-named wheel)
- [ ] F/T re-verified on the new image; cells updated
- [ ] changelog pending entry gated the push; `image_tag` recorded
- [ ] gendoc PR refreshed the generated pages (no hand-edits)
