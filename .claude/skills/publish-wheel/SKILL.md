---
name: publish-wheel
description: >-
  Build and publish a component wheel (flagtree / flag_gems / flagcx / vllm /
  sglang / megatron / plugin / libs / compressor) to a vendor PyPI index,
  including adding a wheel to an existing index and standing up a new publish
  line. Trigger on publish a wheel / build a wheel / upload to pypi / release a
  component / new wheel line / flagos-pypi-*. NOT for: image builds and
  dependency or compiler bumps (see update-backend), rolling an app to a new
  version (see rollout-app-version), or verifying an app cell on a node (see
  verify-app-backend).
---

# Publish a Wheel

## Context

Every component this repo ships is published as a wheel from its own workflow
into a per-vendor Nexus index. The lines differ in what they build and where
they build it; the shape is one shape, and it is the shape a new line copies.
Three rules decide most of the work:

- **The version is a function of the ref, not a typed string.** A wheel version
  comes from the upstream tag (setuptools-scm), from a per-backend release name
  plus a date, or from a pinned input — it is never invented at the call site.
  Which of the three a line uses is that line's own fact, kept in its packaging
  directory.
- **The catalog is written by the recorder, not the publisher.** A publish step
  leaves one manifest line; a single record job per run turns manifests into
  `packaging/packages.yaml`. Never hand-edit the four machine fields.
- **twine never runs on the runner's python.** Use the uploader image
  (`packaging/upload/`) — the reason is in that directory's script and
  Containerfile headers, and it is not a style preference.

## Prerequisites

- The component's packaging directory (`packaging/<component>/`) and its
  README / DESIGN: which ref it builds, which Containerfile, which index.
- Membership in `.github/builders.txt` to trigger the workflow manually.
- For a first publish of a package: the catalog entry's human-owned fields are
  yours to write (§5); the record job only fills the machine ones.

## Standard flow

### 1. Identify the line

The component → workflow → index roster is `.github/workflows/` plus the table
in `CLAUDE.md`; do not keep a second copy of it here. Read the workflow's
header comment before running it — the lines document their own inputs and
their reason for existing there.

Two things to settle before dispatching:

- **which index** the wheel belongs on (`flagos-pypi-<vendor>` for
  vendor-specific builds, `flagos-pypi-hosted` for vendor-neutral ones,
  `flagos-pypi-daily` for the daily lines). Every vendor index is derived from
  the backend key, not passed by hand.
- **which ref** the build takes. A `pull/<N>` ref builds a PR head for
  verification only — that is not a release, and it must not be uploaded.

### 2. Dispatch with the publish switch off first

Most lines default their publish switch to `false` (`upload` on most,
`publish` on flagcx). Run the build once without it: that is the cheap way to
learn the ref compiles, before the publish is a real event.

```bash
gh workflow run <line>.yml -f backend=<backend> -f <ref-input>=<ref>
```

Read the line's own inputs instead of assuming: the flag names, whether a
backend filter exists, and whether a line publishes unconditionally
(`flaggems-release` does — dispatching it is a publish) all differ.

The `authorize` job checks the triggering account against
`.github/builders.txt`. `gh workflow run` returns as soon as the run is queued,
so it exits 0 even when authorization later fails — read the run's job list,
not the dispatch's exit code.

### 3. Where the build happens is the line's business

Some lines build inside the backend's runtime or builder image (needing the
vendor toolchain), some on `ubuntu-latest`. That choice is already made per
line; a new line follows the contract in `packaging/README.md` and the
component's own DESIGN. Do not move an existing line's build environment to
make an upload step simpler.

### 4. Upload through the uploader image

```bash
WHEEL_UPLOAD_REPO=<index> \
WHEEL_UPLOAD_PATHS="/wheels/*.whl" \
bash packaging/upload/upload-wheels.sh
```

with `NEXUS_TOKEN` on the step env. The script's header is the contract
(mount, index root, multiple repos, the slash-free-mount trap); read it rather
than re-deriving a `docker run`. The secret stays a bare `-e NEXUS_TOKEN` so it
never reaches a command line — this is why it is a script and not a composite
action, and why a call site must not inline its own twine.

A few older lines still run twine inside the vendor build image. Do not add a
new one in that shape.

### 5. Leave the manifest line, then let the recorder commit

After twine succeeds, the publish step appends one line per uploaded wheel to
the manifest and uploads it as an artifact; a single record job turns the
manifests into `packaging/packages.yaml`. The line format, the artifact naming,
the merge semantics and which fields are machine-written are all in
`docs/wheel-info.md` — the skill does not restate them.

What the flow decides, and what goes wrong:

- **The publish step never writes the catalog.** It has no write access, and a
  fan-out dispatch would race on one file. Do not "fix" a missing catalog entry
  by editing it from the publish job.
- **The manifest's package name is the catalog name, which the wheel filename
  cannot give you** (`vllm-plugin-fl` vs `vllm_plugin_fl`). The publish step
  spells it; a wrong spelling surfaces as a stub row in the record PR, not at
  upload time.
- **A publish step that fails midway still leaves the manifest of what did get
  uploaded** — deliberate, and the record job's `always()` gate depends on it.

The record job is shared (`record-wheel-info.yml`, `workflow_call`). The call
site carries only what differs: `workflow:`, and — if the run has more than one
record job — a narrower `manifest_pattern`, or the jobs cross-download each
other's manifests. It opens a review-gated PR on `auto/wheel-info-<workflow>`;
merging it, and writing the human-owned fields of a new package's catalog entry,
is the human step.

### 6. Adding a new publish line

A new line copies the shape, not the content: an `authorize` job, a matrix or
prepare job, the build, the upload (via the uploader image), the manifest step,
the artifact upload, and the `record-wheel-info` job with its three gates
(`needs` / `always() && <publish gate> && !cancelled()` / `permissions:
contents + pull-requests write`). `packaging/README.md` §引用维护清单 and the
`CLAUDE.md` workflow table are both touched in the same PR — the table is
contract, not documentation debt.

## Facts index

- Catalog mechanics, manifest convention, recorded vs human fields:
  `docs/wheel-info.md`
- Workflow roster and what each line publishes: `CLAUDE.md` workflow table
- Uploader image contract and the twine rationale: `packaging/upload/`
  (`Containerfile`, `upload-wheels.sh`, `image-ref.sh`), `wheel-uploader.yml`
- Per-line build facts: `packaging/<component>/README.md` / `DESIGN.md`
- FlagTree's three-line split (builder stage → daily wheel → release wheel):
  `packaging/flagtree/README.md` + `packaging/flagtree/backends.yaml`
- Index names and vendor mapping: `configs.yaml`, `.github/build-config.yml`
- Consumer pins: `configs.yaml` `deps:` / `deps_app:`, app `app-versions.yaml`

## Why these exist

- Version-from-ref: a hand-typed version is a second source of truth that
  drifts the moment the ref moves, and it makes "which commit is this wheel?"
  unanswerable. The commit lives in the wheel metadata for exactly this reason.
- Single recorder: a fan-out dispatch publishes from many jobs at once; if each
  committed, they would race on one file. The manifest exists so the publish
  step records an event without needing write access to the catalog.
- Uploader image: the node's system python can be permanently poisoned by a
  twine upgrade, so the ability to publish must not depend on it.
- Manifest `pkg` spelled explicitly: the catalog name and the wheel name are
  not derivable from each other, and a silently wrong one shows up as a stub
  row or a missing entry much later.

## Done when

- The build ran once with the publish switch off, and the ref is the intended
  one.
- Wheels are on the expected index (confirmed by reading the index, not by the
  job's exit code alone).
- Every uploaded wheel left a manifest line carrying the catalog package name.
- The record job opened its PR; a new package's human-owned catalog fields
  (including `sources:`) are written or explicitly handed to a human.
- Any new line's roster entries (`CLAUDE.md` table, `packaging/README.md`) are
  in the same PR.

## Failure modes / escalate

- **A build cannot smoke-test the whole wheel.** Several backends' modules
  abort at import without device nodes or a vendor SDK, so the build asserts
  what it can (install, metadata, a specific artifact) and the real check is
  on-node. Do not read "build green" as "wheel works" — and do not add an
  import smoke to a backend that cannot support one; the reason is recorded per
  backend.
- **Republishing the same version is a replacement, and the server decides
  whether that is allowed.** Nexus on the internal host has redeploy on, so a
  file already on the index is replaced rather than rejected — which is what
  lets a manual run push a fix under the day's own version. Do not add
  `--skip-existing` "for safety": it turns that path into a silent no-op. Where
  redeploy is off, the upload fails and you need a new version, not a retry.
- **An unset/blank `NEXUS_TOKEN`** fails before anything is sent — check the
  step env, not the wheel.
- **A wheel that lands with the wrong tag** (e.g. an `any` platform tag on a
  compiled wheel) is caught only by a line that gates on it; when adding a
  line, add that gate.
- **A manifest line whose `pkg` does not match the catalog** produces a stub
  row — fix the call site's spelling, not the catalog.
- **Adding a wheel to an existing line looks like it publishes and does not.**
  The daily line skips a row whose wheel is already on the index under the same
  version (`flagtree-wheel-daily.yml`); a manual dispatch skips that check only
  where the server has Nexus redeploy on. A silent no-op is the failure to
  expect, so confirm the artifact on the index rather than trusting the job.
- **Downloading a wheel under a generic name breaks the published link.** A
  hosted download serves the file under the `href` basename, and the `#sha256=`
  fragment on the same link is computed over the original bytes. Renaming the
  download to something like `wheel.whl` leaves the index pointing at a name
  that no longer resolves and a checksum that no longer matches. Keep the
  filename the build produced — it is the PEP 427 name for a reason.
