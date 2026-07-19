# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FlagOS container image build infrastructure — **configs.yaml is the single source of truth**.
It builds three layers for 13+ GPU/NPU vendors:

| Layer | What | Built by |
|---|---|---|
| **Base images** | Vendor SDK + toolchain on Ubuntu 24.04 | `base/<vendor>-<backend>` Containerfiles |
| **Runtime images** | Base + Python venv + FlagGems + compilers (FlagTree/Triton) | `runtime/Containerfile` (one for all) |
| **Wheels** | FlagTree (C++ compiler) + FlagGems (pure Python) | `flagtree-builder/`, `flaggems-builder/` |

## Key commands

```bash
# Build a base image locally
python scripts/build_base.py nvidia-cuda12.8 --dry-run    # preview
python scripts/build_base.py nvidia-cuda12.8 --push        # build + push

# Build a runtime image (needs FlagGems source for version derivation)
python scripts/build_runtime.py nvidia-cuda12.8 --flaggems-dir ../FlagGems --dry-run
python scripts/build_runtime.py metax --flaggems-dir ../FlagGems --push   # vendor shorthand (single backend)

# Generate CI matrix from configs.yaml
python scripts/generate_matrix.py                          # all buildable backends
python scripts/generate_matrix.py nvidia-cuda12.8 metax    # subset

# Regenerate the intermediate data file from configs.yaml + Containerfiles
python docs/gen_data.py                                 # → docs/data/images.yaml

# Generate docs pages + in-repo readmes (base/<name>.md, runtime/<name>.md)
python docs/gen_descriptions.py                         # all backends → files
python docs/gen_descriptions.py nvidia-cuda13.3          # one backend → stdout
```

## Architecture

### Data flow (config-driven, no duplication)

```
configs.yaml + base/ Containerfiles + build-config.yml
        │
        ▼
  docs/gen_data.py  ──→  docs/data/images.yaml  ──→  docs/gen_descriptions.py  ──→  Hugo pages + Harbor descriptions
        │
        ├──→  scripts/generate_matrix.py  ──→  CI matrix JSON  ──→  trigger.yml / runtime.yml
        └──→  scripts/build_runtime.py    ──→  --build-arg       ──→  runtime/Containerfile
```

`configs.yaml` owns: vendors, backends, deps, env vars, SDK components, Python version, compiler packages, cmake backend.
`build-config.yml` owns: registry host+prefixes, runner labels per backend, `docker run` flags per vendor, verify commands.
`docs/gen_data.py` parses `configs.yaml` + `base/` Containerfiles (FROM, apt packages, env) + `build-config.yml` to produce `docs/data/images.yaml` — the intermediate data file that feeds doc generation.
`docs/gen_descriptions.py` renders `images.yaml` into per-image markdown (web flavor for Hugo, plain flavor for in-repo + Harbor).

### Image naming

- **Base:** `flagos-base-{vendor}-{backend}:{version}-{n}` — version from Containerfile `LABEL org.opencontainers.image.version` (repo tag), n = per-backend git revision count since that tag. Only Containerfile changes bump n.
- **Runtime:** `flagos-runtime-{vendor}-{backend}:latest`
- Registry: `harbor.baai.ac.cn/{prefix}/` (prefix from `build-config.yml` registry.prefixes)
- `base/<name>` Containerfile names match the `{vendor}-{backend}` key (e.g. `base/nvidia-cuda12.8`)

### Base image version (per-backend, not global)

Each Containerfile declares `LABEL org.opencontainers.image.version="X.Y.Z"`. `scripts/version.py` computes the full version: reads the LABEL + counts commits to that file since tag `vX.Y.Z`. The repo tag anchors all backends at the same X.Y.Z baseline; n diverges per-backend as Containerfiles evolve independently. See `scripts/version.py` for the implementation.

### Runtime Containerfile (multi-stage, dual-compiler)

`runtime/Containerfile` is a single file for all backends. `scripts/build_runtime.py` resolves build args from `configs.yaml`:
- `BASE_IMAGE` — the base image ref (built from same git tag)
- `DEPS` — space-separated vendor packages from `configs.yaml deps:` (explicit, no extras — extras are unreliable across vendor indexes)
- `CPP_EXTRA` — e.g. `cpp-cuda`, derived from `cmake_backend`
- `FLAGTREE_PKG` / `TRITON_PKG` — compiler packages

Two stages: **builder** (installs uv, venv, deps, compilers, FlagGems wheel) → **runtime** (copies venv + uv). When both compilers are configured, FlagTree is default (`/flagos`) and Triton is a side install (`/opt/triton`), switchable via the `compiler` shell function.

### CI workflows (manual trigger, not push-driven)

- **`trigger.yml`** — Base Image Build (manual). `workflow_dispatch` with backend + push inputs. Generates matrix via `generate_matrix.py`, calls reusable `imagebuild.yml` per backend.
- **`runtime.yml`** — Runtime Image Build (manual). Same pattern, additionally checks out FlagGems repo for version derivation.
- **`flaggems-wheel.yml`** — Daily (01:17 UTC) + manual FlagGems wheel build + upload to `flagos-pypi-daily` via twine.
- **`base-descriptions.yml`** — Triggered on base image build completion. Extracts system package versions from built images (`dpkg-query`), runs `gen_data.py` + `gen_descriptions.py`, opens a **review-gated PR** with the version diff. Publication to Harbor (`base-descriptions-publish.yml`) only happens when that PR lands on `main`.
- **`hugo-site.yaml`** — Builds + deploys docs site to GitHub Pages (triggered on push to `main` when `docs/**`, `configs.yaml`, or `base/**` changes).

### Runners

All self-hosted: default is `[self-hosted, h20]` (x86_64). Ascend backends override to aarch64 CANN nodes (`cann850` / `cann9`). Defined in `build-config.yml` runners.overrides.

### Adding a new backend

1. Add the vendor SDK to a `base/<vendor>-<backend>` Containerfile
2. Add the backend spec to `configs.yaml` under `vendors.<vendor>.<backend>`
3. Add to `docs/data/images.yaml` (display metadata, launch commands)
4. Add runner override in `build-config.yml` if needed (arch or GPU-specific)

## Conventions

- **Version = Containerfile LABEL + git count.** Each `base/<name>` has `LABEL org.opencontainers.image.version="X.Y.Z"`. `scripts/version.py` computes the per-backend version as `X.Y.Z-n` where n = commits to that file since tag vX.Y.Z. CI needs `fetch-depth: 0`.
- **Reset at release.** Moving the repo tag (`vX.Y.Z`) and updating all LABELs resets n to 0 across all backends. A `sed` across all Containerfiles is the release procedure.
- **Per-vendor PyPI indexes.** Each vendor has a separate index: `flagos-pypi-{vendor}`. This isolates vendor-specific packages so there is no cross-vendor package confusion.
- **No extras for runtime deps.** `configs.yaml deps:` lists explicit packages passed to `uv pip install` — extras (`.[nvidia-cuda128]`) can't resolve correctly across vendor indexes.
- **FlagTree is the default compiler.** Triton is the fallback (installed to `/opt/triton` when both present). The `compiler` bash function toggles.
- **Wheel-based install for runtime.** FlagGems is installed from PyPI wheels, not from a source checkout. `--flaggems-dir` in `scripts/build_runtime.py` is only for version derivation.
- **`base_source` env = TODO.** Some vendors (ascend, hygon, thead) need a `source set_env.sh` step; the goal is to expand these into base image ENV so users don't need to source.
- **Docs are generated, not hand-written.** `base/<name>.md` and `runtime/<name>.md` are outputs of `docs/gen_descriptions.py`. Edit the generator or data files, not the markdown.
- **Review-gated descriptions.** System package versions are extracted from built images and injected into description PRs. Human review of version bumps happens before descriptions go live on the docs site or Harbor.
- **Apache 2.0 license.** All source files carry the license header. `license-tool/` provides header scanning + auto-adding.
