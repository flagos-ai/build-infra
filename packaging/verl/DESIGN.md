# verl packaging — design

Status: **planned.** The design is confirmed (2026-08-27) but the build/verify
facilities are not landed yet — no `builder/`, no `Containerfile`, no workflow, no
status matrix on `main`. `docs/verl-app-image-plan.md` is the implementation plan;
`docs/verl-hygon-e2e.md` is the first (and so far only) backend E2E report. This file
is the design of record — the decisions behind that plan, so the plan can be read
for its *what* and this file for its *why*.

Goal: ship verl-FL (the full-stack RL training framework) as app images — runtime
image plus a **single-step `pip install`** of a wheel built from the fork — alongside
megatron-core and vllm, without disturbing the runtime's torch/triton/flag_gems/numpy
matrix.

## Context

verl is a **fork-source** path, like megatron and unlike vllm/sglang (which repack an
sdist). The one fact that decides almost everything downstream: verl is a **pure Python
package** (no pybind11 extension — `pybind11` is only a pip dependency). So its wheel is
`py3-none-any`, **one wheel for all 17 backends**, with no megatron-style cp310/cp311/cp312
split and no ABI contract to build against.

verl-FL composes three engines, all already in the FlagOS stack:
- **training** — `MegatronFLEngineWithLMHead` over `megatron.core` + TransformerEngine-FL
  (`TE_FL_PREFER=flagos`),
- **rollout** — vllm + vllm-plugin-fl (`VLLM_FL_OOT_ENABLED=1`),
- **platform** — `VERL_PLATFORM` (`cuda` / `npu` / `musa` / `cpu`).

Its own deps (ray/datasets/peft/tensordict/torchdata/wandb/tensorboard/pandas/
hydra-core/accelerate/codetiming/dill/pylatexenc) are not in the runtime image, so they
ride `deps_app.verl0.7.0`.

### Decisions taken

| Question | Decision |
|---|---|
| Wheel model | **Fork-source, not repack.** `flagos-ai/verl-FL` (verl v0.7.0, fork describe `v0.2.0-rc2.post1-1-g45068d9e`). No sdist to repack; the fork's `setup.py` `numpy<2.0.0` is satisfied by the runtime's stack-wide pin, so the install resolves without METADATA surgery |
| Version | `0.7.0+fl.<date>.g<sha>` — public segment = upstream verl version, local label = fork provenance (megatron convention). `VERL_VERSION` input overrides for release |
| Build environment | Any runtime image (e.g. `nvidia-cuda12.8`). Pure Python means build env == delivery env does not bind, but the Containerfile still does a `requires-python` gate + smoke install |
| numpy<2.0.0 | **Naturally satisfied, no `--no-deps`.** verl's `install_requires` caps numpy at 2.0.0; the runtime matrix already pins `numpy==1.26.4` stack-wide (a runtime-layer decision), so pip validates without downgrading anything. The older `--no-deps` necessity was an artifact of the pre-pin `numpy==2.3.5` runtime |
| megatron-core | **Base, not `[rl]`.** verl's every megatron import is `megatron.core.*`; it never touches `megatron.rl`. The `[rl]` extra exists only for Megatron's own RL orchestration, and its pinned versions would *downgrade* verl's own locked deps (datasets/pyarrow/transformers/wandb) — pure churn |
| rollout vllm | **Fork-side branch route.** verl 0.7.0's vllm gate caps at 0.12.0 while vllm-plugin-FL floors at 0.13.0 — intersection empty, so "verl's own 0.11/0.12 line + plugin" cannot combine. Patch the verl-FL fork's version gate to the 0.20.2 line (2 files, 4 touch points) and reuse `vllm==0.20.2+flagos` + the existing plugin wheel. This is a **build-infra fork-branch** patch; whether/when it enters verl-FL mainline is the verl-FL team's call |
| TE-FL | **Independent pure-Python wheel.** `TE_FL_SKIP_CUDA=1` → `ext_modules=[]` → `py3-none-any`, one wheel for all backends (`2.17.0+fl.<date>.g<sha>`, `packaging/transformer-engine-fl/builder/`). megatron-core does not carry TE-FL, and verl imports it lazily in try/except, so it is an optimisation layer, not a hard requirement |
| FlagCX | **No hard dependency.** The only reference is a lazy `from vllm_fl … import PyFlagcxCommunicator` (ships in vllm-plugin-fl). FlagCX is just the comm-backend string selected when `USE_FLAGCX=1`; the default falls back to vendor-native nccl/hccl/mccl. `USE_FLAGCX`/`FLAGCX_PATH` must be paired (`is_flagcx_enabled()` asserts) |
| app key | `verl0.7.0` (version in the key, vllm0.20.2 precedent) → `flagos-app/verl0.7.0-{vendor}-{backend}:{stack_version}-{fork_ver}` |
| Verification | `verify-verl-backend.sh` on the backend's node: matrix-unchanged (torch/triton/flag_gems/numpy) + `import megatron.core`/`vllm`/`verl` + platform probe, then a minimal `main_ppo` E2E on **both** compilers (flagtree and triton). Cells stay ⬜ until F/T dual-path passes |

## Not here

- The verl-FL source itself — the wheel build clones the fork and overlays only the
  version-gate patch + `stamp_version.py`, same as megatron.
- TE-FL — its own wheel line (`packaging/transformer-engine-fl/`), referenced but not owned
  by verl.
- The rollout vllm 0.11/0.12 line — verl-FL mainline keeps it; build-infra rides the
  0.20.2 branch route only.

## See also

- `packaging/verl/docs/verl-app-image-plan.md` — the implementation plan (Containerfile,
  configs.yaml, docs hooks, workflow, verify script, risks).
- `packaging/verl/docs/verl-hygon-e2e.md` — the first backend E2E report (6 patches + 1 env
  var to full GRPO on hygon, both compiler paths).
- `packaging/megatron/DESIGN.md` — the fork-source precedent verl mirrors.
- Docs site: Design → verl (operator summary, links back here).
