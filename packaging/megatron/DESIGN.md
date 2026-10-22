# Megatron packaging — design

Status: **implemented.** The `docs/` tree is the operator-facing companion (verification
reports, playbooks, per-backend records); `builder/README.md` is how to run the wheel build;
this file is the design of record — why, not what. `builder/Containerfile` and the two app
Containerfiles are the live code.

Goal: ship megatron-core (the Megatron-LM-FL fork) as app images — runtime image plus a
**single-step `pip install`** of a wheel built from the fork — without repacking the wheel
or disturbing the runtime's torch/triton/flag_gems matrix.

## Context

megatron-core ships a compiled extension (`megatron.core.datasets.helpers_cpp`, pybind11), so
the wheel is CPython-ABI-specific (`cp310` / `cp311` / `cp312`, never `py3-none-any`). That one
fact decides almost everything downstream: which Pythons get built, where the build runs, and
what the anti-silent-skip gate has to look for.

megatron is a **fork-source** path, unlike vllm/sglang which repack an sdist. The distinction is
the whole design: the fork's `pyproject.toml` keeps `torch>=2.6.0` in `Requires-Dist`, the
runtime's vendor torch satisfies it, and pip resolves zero packages — so the install can be
single-step with no `--no-deps` and no METADATA surgery.

### Decisions taken

| Question | Decision |
|---|---|
| Wheel model | **Fork-source, not repack.** The wheel keeps `torch>=2.6.0`; the runtime's vendor torch satisfies it, pip resolves nothing. The vllm/sglang repack exists because an sdist's deps would pull public-PyPI torch over the vendor build — megatron has no such sdist path. The repack facility was removed (2026-08-14) |
| Version | `0.17.1+fl.<date>.g<sha>` — the public segment is the upstream megatron-core version, the local label is the fork-commit provenance (date + exact sha). PEP 440 ignores the local label in `==0.17.1` matching, so existing pins keep resolving. Release builds can override with `MLF_VERSION` (e.g. `0.18.2+0.3.0`, the `fl` dropped for that line by explicit user call) |
| Build environment | **The backend's runtime image itself** (`flagos-runtime-{vendor}-{backend}:{version}`). No separate toolchain/builder image — the `megatron-builder-*` concept image was never built. The runtime carries the exact Python + torch + `pybind11==3.0.3` the wheel runs against, so build env == delivery env and the ABI contracts match by construction |
| helpers_cpp | **Mandatory, not optional.** `setup.py` declares the extension `optional=True`, so a failed compile is silently skipped; `megatron/core/datasets/helpers.py` imports it unconditionally, so the skip produces a broken wheel. The Containerfile gates on the `.so` being inside the wheel |
| ABI pins | `pybind11==3.0.3` (matches `configs.yaml` runtime_prereqs; a 3.1.0 build bumped internals v11→v12 and breaks at call time — the flagtree-builder lesson), `numpy==1.26.4` (build against 1.x headers so the `.so` runs on both 1.x and 2.x runtimes), `setuptools<80` + `packaging>=24.2` (match the pyproject build-system requires for `--no-build-isolation`) |
| requires-python | The fork's `pyproject.toml` declares `>=3.12` (an upstream uv-sync tightening). Patched **on the fly** to `>=3.10` after clone, before build — pip enforces Requires-Python at install, so cp310/cp311 wheels would otherwise be refused. The fork repo itself stays untouched (relaxing it there is a proposed follow-up) |
| Wheel install (app) | Single-step `pip install "megatron-core[training|rl]==${MEGATRON_VERSION}"` from the vendor PyPI, **no `--no-deps`** — the extra selects the scenario deps (`[training]` = modelopt/tqdm/datasets; `[rl]` = GRPO). The exact pin carries the local label, because a plain `0.17.1` is satisfied by every fork build of that version and pip would pick the greatest local version on the index |
| scipy guard | `scipy<1.18` rides the same install: modelopt's unconstrained scipy dep resolves 1.18+ (numpy>=2.0.0) since 2026-08, which would upgrade the runtime's stack-wide `numpy==1.26.4` pin and corrupt the inert matrix |
| PYTHONPATH triton | The wheel-install and APP_DEPS steps run under dash (no BASH_ENV, so no compiler on PYTHONPATH); pip must see the side-dir triton dist-info (`/opt/triton`) or torch's `triton==N` Requires-Dist pulls a fresh triton into site-packages, bypassing the vendor triton |
| Anti-silent-skip gates | (1) `.so`-in-wheel gate — a `zipfile` scan (runtime images lack `unzip`) finds `helpers_cpp*.so`; (2) smoke test — install the wheel with the full single-step `pip install` and load `helpers_cpp` via `importlib` (importing `megatron.core` needs the vendor SDK env, which `docker build` RUN can't source; that check belongs to `verify-megatron-backend.sh`) |
| Verification | `verify-megatron-backend.sh` on the backend's node, `--app-image` mode: BEFORE = runtime, AFTER = app package matrix unchanged + `megatron.core` import + `helpers_cpp` bindings. Push is gated on this. Cell states live in `status_matrix.*.yaml` → `docs/megatron-verification-matrix.md` |

## Not here

- The Megatron-LM-FL source itself — the wheel build clones the fork and overlays only a
  `requires-python` sed patch + `patch-compile-helpers-sysconfig.py` (MLF PR #112 on the fly) +
  `stamp_version.py`. The fork is not modified.
- The RL line: megatron_rl is **paused** (2026-08-31 decision) — RL moved to verl; the
  megatron RL matrix column is ⏸.

## See also

- `packaging/megatron/builder/README.md` — how to run the wheel build, per-backend.
- `packaging/megatron/builder/Containerfile` — the build (clone → patch → stamp → wheel → gates).
- `packaging/megatron/docs/README.md` — the verification-doc entry point, per-version.
- `packaging/megatron/docs/megatron-0.17.1/decisions.md` — the ADR record (fork vs repack,
  helpers_cpp, no-deps, version format).
- `app/megatron/Containerfile.megatron-training` / `Containerfile.rl` — the app install.
- Docs site: Design → Megatron (operator summary, links back here).
