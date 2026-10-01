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

`packaging/flagcx/` sits beside these layers rather than in them: it builds **FlagCX itself**,
one backend per container, in three channels — `.deb` packages out of the backend's **base**
image, wheels for the vendor PyPI out of its **runtime** image, and, for rows whose runtime image
carries no device toolchain at all (the nvidia ones), the build-toolchain images that the wheel
build then runs in. Design and the `backends.yaml` field contract live in
`packaging/flagcx/DESIGN.md` (deb) and `packaging/flagcx/WHEEL-DESIGN.md` (wheel + builder).

## Agent 协作纪律

agent 写作/记录的唯一权威规则见 `docs/agent-protocol.md`。开箱即知：

- **subagent 永不写 docs / memory / WORKING-CONTEXT** —— 写入判断收归主会话。
- **只记结论**（为什么 / 最终状态 / 机制），**不记过程**（流水账禁止）。
- **注释只写为什么**，不解释是什么；密度匹配周围代码。
- 每线 `docs/README.md` 是唯一入口；先 grep 定位再读最小片段。
- WORKING-CONTEXT 类文件有时效：并入 docs / status matrix 后**删除**。

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

## Skills (flow templates + index; facts live in docs)

Project skills live in `.claude/skills/<name>/SKILL.md` (loaded on demand).
A skill is a judgment/iteration flow — what to do, in what order, when to stop
and ask. Facts (per-backend records, versions, decisions) stay in the docs each
skill references; skills never duplicate them (agent-protocol layer 1).

| Skill | Trigger | Docs entry |
|---|---|---|
| `node-ops` | ssh to a verify node, drive a debug container, repro a failed cell | `scripts/verify-nodes.example.yaml`, `docs/verify-orchestrator.md` §5 |
| `reporting` | write a report / PR body / commit message / chat summary | `docs/agent-protocol.md` |
| `update-backend` | bump deps/compiler/SDK/version for a backend or across backends; add a new backend (rare) | `configs.yaml`, `scripts/base_image_status.py`, `docs/status-matrix.md` |
| `verify-app-backend` | walk a status-matrix cell to F/T-passed + symbol write-back | `docs/status-matrix.md`, `docs/verify-orchestrator.md` |

Loading discipline: check the skill before acting; facts a skill references
are read from the docs it names, never restated inside the skill.

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

`configs.yaml` owns: vendors, backends, deps, env vars, SDK components, Python version, compiler packages, cmake backend, and the app-layer public naming (`app_public`).

`build-config.yml` owns: registry host+prefixes, runner labels per backend, `docker run` flags per vendor, verify commands.

`docs/gen_data.py` parses `configs.yaml` + `base/` Containerfiles (FROM, apt packages, env) + `build-config.yml`
to produce `docs/data/images.yaml` — the intermediate data file that feeds doc generation.

`docs/gen_descriptions.py` renders `images.yaml` into per-image markdown (web flavor for Hugo, plain flavor for in-repo + Harbor).

### Image naming

- **Base:** `flagos-base-{vendor}-{backend}:{version}` — version from configs.yaml `version:`.
  All backends share the same flat tag during a release cycle; rebuilt images overwrite it.
  (A per-backend `-N` commit-count affix was tried and dropped as confusing.)

- **Runtime:** `flagos-runtime-{vendor}-{backend}:{version}` — version from configs.yaml `version:` (same as base)

- **App:** `flagos-app/{app}{app_version}-{app_name}:{version}` — `{app_name}` is the backend's
  **app-layer public name** (`scripts/app_public.py`, from configs.yaml `app_public`), not the
  backend key: the app layer is published vendor-neutral, so `nvidia-cuda12.8` publishes as
  `generic-12.8`. Base and runtime keep the real name, and so does everything that addresses the
  backend — runner label, status-matrix key, Containerfile, `--backend`. `app_name` reaches
  only the image tag, the changelog filename and the launch page.

- Registry: `harbor.baai.ac.cn/{prefix}/` (prefix from `build-config.yml` registry.prefixes)

- `base/<name>` Containerfile names match the `{vendor}-{backend}` key (e.g. `base/nvidia-cuda12.8`)

### Base image version (flat, stack-wide)

`configs.yaml` declares `version: "X.Y.Z"` — the single stack-wide release version.
Every base image carries the same flat `X.Y.Z` tag, stamped as an OCI label at build time
(Containerfiles do not hardcode it).
Because rebuilt images overwrite the same tag, whether a pushed image is stale is answered by
`scripts/base_image_status.py` — it reads the `revision`/`version` OCI labels off the pushed image
and diffs the corresponding `base/<name>` Containerfile since that commit.

### Runtime Containerfile (multi-stage, dual-compiler)

`runtime/Containerfile` is a single file for all backends. `scripts/build_runtime.py`
resolves build args from `configs.yaml`:

- `BASE_IMAGE` — the base image ref (built from same git tag)
- `DEPS` — space-separated vendor packages from `configs.yaml deps:`
  (explicit, no extras — extras are unreliable across vendor indexes)
- `CPP_EXTRA` — e.g. `cpp-cuda`, derived from `cmake_backend`
- `FLAGTREE_PKG` / `TRITON_PKG` — compiler packages
- `FLAGGEMS_VERSION` — from `configs.yaml` `flaggems:`, override with `--flaggems`

Two stages: **builder** (installs uv, venv, deps, compilers, FlagGems wheel) → **runtime** (copies venv + uv).
When both compilers are configured, FlagTree is default (`/flagos`) and Triton is a side install (`/opt/triton`),
switchable via the `compiler` shell function.

### CI workflows (manual trigger, not push-driven)

All `.github/workflows/*.yml`. Workflow names differ from filenames; the release
playbook (`docs/release-workbook.md`) references the display names.

| Workflow file | Purpose |
|---|---|
| `base-image.yml` | Base Image Build (manual): matrix via `generate_matrix.py`, one job per backend; build logic (Harbor login, disk guard, `build_base.py`) inlined in the same file |
| `runtime-image.yml` | Runtime Image Build (manual): base + FlagGems wheel (`flaggems=none` → `-build` tag) |
| `gendoc-base.yml` / `gendoc-runtime.yml` | Extract system package versions from built images → review-gated description PR |
| `pubdoc-base.yml` / `pubdoc-runtime.yml` | Publish descriptions to Harbor on the PR landing on `main` |
| `hugo-site.yml` | Build + deploy docs site to GitHub Pages (push to `main`, `docs/**` / `configs.yaml` / `base/**`) |
| `megatron-wheel.yml` | Build megatron-core wheels in the backend's runtime image, upload to `flagos-pypi-hosted` |
| `megatron-app-image.yml` / `vllm-app-image.yml` / `sglang-app-image.yml` | Build app images from the runtime + vendor wheel, verify on-node, push `flagos-app/...` |
| `flagcx-*` (`deb.yml`, `wheel.yml`, `builder.yml`, `rpm.yml`) | FlagCX `.deb` / wheel / build-toolchain / `.rpm` lines (see `packaging/flagcx/DESIGN.md` + `WHEEL-DESIGN.md`) |
| `flaggems-wheel.yml` | Daily (01:17 UTC) + manual FlagGems wheel build → `flagos-pypi-daily` |
| `flaggems-release.yml` | FlagGems release wheels: python + cpp wheels → all vendor indexes, `update-config` PR |
| `native-deb.yml` / `native-rpm.yml` / `noarch-deb.yml` / `noarch-rpm.yml` | Component repos' deb/rpm release paths to the Nexus repositories |
| `sglang-wheel.yml`, `vllm-wheel.yml`, `vllm-plugin-wheel.yml`, `flagtree-wheel.yml`, `flash-attn-wheel.yml`, `flaglibs-wheel.yml` | Per-component wheel builds to the vendor PyPI indexes |
| `verify-runtime.yml` / `verify-driver.yml` / `verify-cpp-fixes.yml` / `status-matrix-consistency.yml` | Verify image content, driver reachability, cpp fixes, status-matrix drift |
| `upload-nexus.yml`, `sync-to-remote.yaml`, `auto-approve.yml`, `release-verify-selftest.yml`, `sdk-reminder.yml` | Nexus upload, GitCode sync, maintainer-PR auto-approve, release self-test, SDK reminder |

`builders.txt` lists the GitHub accounts allowed to manually trigger the image
build workflows (checked by `authorize` in each workflow).

### Runners

All self-hosted: default is `[self-hosted, h20]` (x86_64).
Ascend backends override to aarch64 CANN nodes (`cann850` / `cann9`). Defined in `build-config.yml` runners.overrides.

### Adding a new backend

The full flow (including the far more common update/upgrade path) lives in
the `update-backend` skill (`.claude/skills/update-backend/`). Minimal shape
for an add: base Containerfile → configs.yaml `vendors.<vendor>.<backend>`
(deps/env/deps_app/compilers) → `build-config.yml` runner override + device
flags → matrix smoke → status-matrix declaration → runtime F/T verify loop →
app layer (`deps_app`). Verify-first, record-after: a backend's cells go ⬜
until on-node dual-compiler verification passes.

## Conventions

- **Version from configs.yaml.** `configs.yaml` `version:` is the single stack-wide release version;
  all images share it as their flat tag.
  At release: bump `version:` and `flaggems:` in one place → `git tag vX.Y.Z`.

- **FlagGems version from configs.yaml.** `configs.yaml` `flaggems:` sets the wheel version for runtime builds.
  Override with `--flaggems` CLI flag when needed.

- **Per-vendor PyPI indexes.** Each vendor has a separate index: `flagos-pypi-{vendor}`.
  This isolates vendor-specific packages so there is no cross-vendor package confusion.

- **No extras for runtime deps.** `configs.yaml deps:` lists explicit packages passed to `uv pip install` —
  extras (`.[nvidia-cuda128]`) can't resolve correctly across vendor indexes.

- **FlagTree is the default compiler.** Triton is the fallback (installed to `/opt/triton` when both present).
  The `compiler` bash function toggles.

- **Wheel-based install for runtime.** FlagGems is installed from PyPI wheels.
  `--flaggems` pins the exact wheel version.

- **Docs are generated, not hand-written.** `base/<name>.md` and `runtime/<name>.md` are outputs of `docs/gen_descriptions.py`.
  Edit the generator or data files, not the markdown.
  Generated web pages carry a provenance marker, and the generator refuses to overwrite a page without one —
  hand-written pages live in the same directories (the app tree has several), and a name collision would
  otherwise be a silent clobber. Give a hand-written page its own name rather than one a backend key derives.

- **Review-gated descriptions.** System package versions are extracted from built images and injected into description PRs.
  Human review of version bumps happens before descriptions go live on the docs site or Harbor.

- **Apache 2.0 license.** All source files carry the license header. `license-tool/` provides header scanning + auto-adding.
