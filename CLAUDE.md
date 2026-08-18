# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FlagOS container image build infrastructure — **configs.yaml is the single source of truth**.
It builds four layers for 13+ GPU/NPU vendors:

| Layer | What | Built by |
|---|---|---|
| **Base images** | Vendor SDK + toolchain on Ubuntu 24.04 | `base/<vendor>-<backend>` Containerfiles |
| **Runtime images** | Base + Python venv + FlagGems + compilers (FlagTree/Triton) | `runtime/Containerfile` (one for all) |
| **Wheels** | FlagTree (C++ compiler) + FlagGems (pure Python) + Megatron-LM-FL (pybind11 ext) | `packaging/flagtree/`, `packaging/flaggems/`, `packaging/megatron/builder/` |
| **App images** | Runtime + megatron-core installed single-step from the vendor PyPI wheel (no repack), one Containerfile per app | `app/megatron/Containerfile.megatron-training` / `app/megatron/Containerfile.rl` (mirrors `packaging/vllm/` + `app/vllm/`) |

## Key commands

```bash
# Build a base image locally
python scripts/build_base.py nvidia-cuda12.8 --dry-run    # preview
python scripts/build_base.py nvidia-cuda12.8 --push        # build + push

# Build a runtime image (FlagGems version from configs.yaml, or override)
python scripts/build_runtime.py nvidia-cuda12.8 --dry-run
python scripts/build_runtime.py metax --push                     # vendor shorthand
python scripts/build_runtime.py nvidia-cuda12.8 --flaggems 5.4.0.dev601+g03122362d

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

- **Base:** `flagos-base-{vendor}-{backend}:{version}` — version from configs.yaml `version:`. All backends share the same flat tag during a release cycle; rebuilt images overwrite it. (A per-backend `-N` commit-count affix was tried and dropped as confusing.)
- **Runtime:** `flagos-runtime-{vendor}-{backend}:{version}` — version from configs.yaml `version:` (same as base)
- Registry: `harbor.baai.ac.cn/{prefix}/` (prefix from `build-config.yml` registry.prefixes)
- `base/<name>` Containerfile names match the `{vendor}-{backend}` key (e.g. `base/nvidia-cuda12.8`)

### Base image version (flat, stack-wide)

`configs.yaml` declares `version: "X.Y.Z"` — the single stack-wide release version. Every base image carries the same flat `X.Y.Z` tag, stamped as an OCI label at build time (Containerfiles do not hardcode it). Because rebuilt images overwrite the same tag, whether a pushed image is stale is answered by `scripts/base_image_status.py` — it reads the `revision`/`version` OCI labels off the pushed image and diffs the corresponding `base/<name>` Containerfile since that commit.

### Runtime Containerfile (multi-stage, dual-compiler)

`runtime/Containerfile` is a single file for all backends. `scripts/build_runtime.py` resolves build args from `configs.yaml`:
- `BASE_IMAGE` — the base image ref (built from same git tag)
- `DEPS` — space-separated vendor packages from `configs.yaml deps:` (explicit, no extras — extras are unreliable across vendor indexes)
- `CPP_EXTRA` — e.g. `cpp-cuda`, derived from `cmake_backend`
- `FLAGTREE_PKG` / `TRITON_PKG` — compiler packages
- `FLAGGEMS_VERSION` — from `configs.yaml` `flaggems:`, override with `--flaggems`

Two stages: **builder** (installs uv, venv, deps, compilers, FlagGems wheel) → **runtime** (copies venv + uv). When both compilers are configured, FlagTree is default (`/flagos`) and Triton is a side install (`/opt/triton`), switchable via the `compiler` shell function.

### CI workflows (manual trigger, not push-driven)

- **`trigger.yml`** — Base Image Build (manual). `workflow_dispatch` with backend + push inputs. Generates matrix via `generate_matrix.py`, calls reusable `imagebuild.yml` per backend.
- **`runtime.yml`** — Runtime Image Build (manual). Same pattern, additionally checks out FlagGems repo for version derivation.
- **`flaggems-wheel.yml`** — Daily (01:17 UTC) + manual FlagGems wheel build + upload to `flagos-pypi-daily` via twine.
- **`megatron-wheel.yml`** — Manual (no schedule; release repo). Builds megatron-core wheels from Megatron-LM-FL (`MLF_REF` input), one per backend in the runtime matrix — the build environment **is** the backend's runtime image (`BASE_IMAGE = flagos-runtime-{vendor}-{backend}:{version}`, no toolchain image). Uploads to `flagos-pypi-hosted` via twine when `upload=true`. All three cp-version wheels must be uploaded — the package ships a compiled `helpers_cpp` extension. Whether one cpXXX wheel is shareable across the backends running that Python is decision 6, not yet validated.
- **`megatron-app-image.yml`** — Manual. STUB — structure landed only; builds `flagos-app/megatron-{vendor}-{backend}:{version}` from `flagos-runtime-{vendor}-{backend}` by installing the megatron-core wheel single-step (no `--no-deps`; the wheel keeps `torch>=2.6.0` and the vendor torch satisfies it). The build/verify steps are filled during the hygon25 verification phase (see `packaging/megatron/docs/`).
- **`gendoc-base.yaml`** — Triggered on base image build completion. Extracts system package versions from built images (`dpkg-query`), runs `gen_data.py` + `gen_descriptions.py`, opens a **review-gated PR** with the version diff. Publication to Harbor (`pubdoc-base.yaml`) only happens when that PR lands on `main` (push to `base/*.md`).
- **`gendoc-runtime.yaml`** — Runtime twin of `gendoc-base.yaml` (manual trigger; runtime images rebuild often during FlagGems testing, so no auto `workflow_run`). Opens a review-gated PR with `runtime/*.md`. Publication to Harbor (`pubdoc-runtime.yaml`) happens when that PR lands on `main` (push to `runtime/*.md`).
- **`hugo-site.yaml`** — Builds + deploys docs site to GitHub Pages (triggered on push to `main` when `docs/**`, `configs.yaml`, or `base/**` changes).

### Runners

All self-hosted: default is `[self-hosted, h20]` (x86_64). Ascend backends override to aarch64 CANN nodes (`cann850` / `cann9`). Defined in `build-config.yml` runners.overrides.

### Adding a new backend

1. Add the vendor SDK to a `base/<vendor>-<backend>` Containerfile
2. Add the backend spec to `configs.yaml` under `vendors.<vendor>.<backend>`
3. Add to `docs/data/images.yaml` (display metadata, launch commands)
4. Add runner override in `build-config.yml` if needed (arch or GPU-specific)

## Conventions

- **Version from configs.yaml.** `configs.yaml` `version:` is the single stack-wide release version; all images share it as their flat tag. At release: bump `version:` and `flaggems:` in one place → `git tag vX.Y.Z`.
- **FlagGems version from configs.yaml.** `configs.yaml` `flaggems:` sets the wheel version for runtime builds. Override with `--flaggems` CLI flag when needed.
- **Per-vendor PyPI indexes.** Each vendor has a separate index: `flagos-pypi-{vendor}`. This isolates vendor-specific packages so there is no cross-vendor package confusion.
- **No extras for runtime deps.** `configs.yaml deps:` lists explicit packages passed to `uv pip install` — extras (`.[nvidia-cuda128]`) can't resolve correctly across vendor indexes.
- **FlagTree is the default compiler.** Triton is the fallback (installed to `/opt/triton` when both present). The `compiler` bash function toggles.
- **Wheel-based install for runtime.** FlagGems is installed from PyPI wheels. `--flaggems` pins the exact wheel version.
- **`base_source` env = TODO.** Some vendors (ascend, hygon, thead) need a `source set_env.sh` step; the goal is to expand these into base image ENV so users don't need to source.
- **Docs are generated, not hand-written.** `base/<name>.md` and `runtime/<name>.md` are outputs of `docs/gen_descriptions.py`. Edit the generator or data files, not the markdown.
- **Review-gated descriptions.** System package versions are extracted from built images and injected into description PRs. Human review of version bumps happens before descriptions go live on the docs site or Harbor.
- **Apache 2.0 license.** All source files carry the license header. `license-tool/` provides header scanning + auto-adding.
