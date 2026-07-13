---
title: Vendor onboarding
weight: 10
---

# Vendor onboarding

How to add a new vendor/backend to the FlagOS base image pipeline. You provide:

1. A **base containerfile** — `base/<vendor>-<backend>`
2. A **backend entry** in `configs.yaml` (dependencies / build settings)
3. *(optional)* a **runner override** in `.github/build-config.yml`

After it merges, a maintainer builds the image on demand. No per-vendor JSON or
matrix scripting is needed — the build matrix is derived from `configs.yaml` +
`base/`.

## How the pipeline works

- `base/generate_matrix.py` reads `configs.yaml` and emits one build-matrix entry
  per backend that has a `base/<vendor>-<backend>` file (backends without one are
  skipped). `runson` and the registry come from `.github/build-config.yml`.
- `.github/workflows/trigger.yml` is a **manual** (`workflow_dispatch`) build: pick
  a backend (or `all`) and whether to push.
- Each entry runs `python base/build.py <vendor>-<backend> [--push]`, which reads
  the registry from `.github/build-config.yml`, the version/revision from the
  containerfile's OCI labels, and tags the image
  `flagos-base-<vendor>-<backend>:<version>-<revision>`.

## Naming

| Item               | Convention                                              |
|--------------------|---------------------------------------------------------|
| Base containerfile | `base/<vendor>-<backend>` (e.g. `base/nvidia-cuda12.8`) |
| Image tag          | `flagos-base-<vendor>-<backend>:<version>-<revision>`   |
| configs.yaml key   | `vendors.<vendor>.<backend>`                            |

The `<backend>` segment is the SDK/toolkit version (e.g. `cuda12.8`, `cann9.0.0`,
`neuware4.4.3`) and must match between the `base/` filename and the `configs.yaml`
key.

## Step 1 — add the base containerfile

Create `base/<vendor>-<backend>`, modelled on an existing one (e.g.
`base/nvidia-cuda12.8`). It **must** include these OCI labels:

```dockerfile
LABEL org.opencontainers.image.authors="FlagOS contributors"
LABEL org.opencontainers.image.version="<version>"
LABEL org.opencontainers.image.revision="<revision>"
```

- `version` / `revision` produce the image tag `…:<version>-<revision>`.
- **Bump `revision` on every change** to an existing containerfile — a PR that
  edits a `base/` file without bumping it fails the `check-revision` check. New
  files start at `revision="0"`.
- Prefer baking the vendor SDK env directly with `ENV` (do not require users to
  `source` a script). Only append `:${LD_LIBRARY_PATH}` when the `FROM` image
  already sets `LD_LIBRARY_PATH` (e.g. `nvcr.io/nvidia/cuda`); a plain `ubuntu:*`
  base has none, so no append is needed.

## Step 2 — add the configs.yaml entry

Add the backend under its vendor in `configs.yaml`. See the header comment in that
file for the full field reference. Minimal shape:

```yaml
vendors:
  <vendor>:
    <backend>:
      extras: <flaggems-pyproject-extra>   # e.g. nvidia-cuda128
      python: "3.12"
      triton: triton==...
      # flagtree / cmake_backend / deps / env as applicable
```

## Step 3 — runner (only if needed)

Base images build on `ubuntu-latest` by default. If a backend needs a specific
arch or hardware (e.g. `ascend` packages are `aarch64`), add an override under
`runners.overrides` in `.github/build-config.yml`:

```yaml
runners:
  overrides:
    <vendor>-<backend>: [self-hosted, <label>...]
```

## Step 4 — open a PR, then build

Open a PR with the new `base/` file and `configs.yaml` entry. After it merges, a
maintainer builds the image on demand via the **Base Image Build (manual)**
workflow (`workflow_dispatch`) — choosing your backend and whether to push. Base
images aren't built automatically on every change.
