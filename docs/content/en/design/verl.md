---
title: verl
weight: 80
---

<!--
 Copyright 2026 FlagOS Contributors

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 -->


The verl app image = runtime image + a **single-step `pip install`** of a wheel
built from the verl-FL fork. verl is pure Python, so the wheel is `py3-none-any`
— **one wheel for all 17 backends**, no per-ABI split. Training rides megatron-core,
rollout rides vllm + vllm-plugin-fl; the platform is chosen by `VERL_PLATFORM`.

## One wheel, one matrix

verl is a **fork-source** package (like megatron, unlike vllm/sglang's repack).
Its `numpy<2.0.0` requirement is already satisfied by the runtime's stack-wide
`numpy==1.26.4` pin, so the install needs no `--no-deps` and no dependency surgery.
The deps verl needs that the runtime doesn't carry (ray/datasets/peft/tensordict/
wandb/…) live in `deps_app.verl0.7.0`.

## Two engines already in the stack

- **megatron-core, base** — verl imports only `megatron.core.*`; it never touches
  `megatron.rl`. The `[rl]` extra would downgrade verl's own locked deps, so it's
  left off.
- **rollout vllm, branch route** — verl 0.7.0's own vllm line (0.11/0.12) has an
  empty intersection with vllm-plugin-FL (≥0.13), so the fork's version gate is
  patched to the 0.20.2 line and the rollout reuses `vllm==0.20.2+flagos` + the
  existing plugin wheel. Whether that patch reaches verl-FL mainline is the verl-FL
  team's call.

## Optional layers

- **TE-FL** — `TE_FL_SKIP_CUDA=1` makes it a `py3-none-any` wheel; it ships
  independently and is an optimisation, not a requirement (verl imports it lazily).
- **FlagCX** — no hard dependency; the default falls back to vendor-native
  nccl/hccl/mccl. When enabled, `USE_FLAGCX` and `FLAGCX_PATH` must be set together.

## Full rationale

The design of record lives beside the code:

- [packaging/verl/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/verl/DESIGN.md) — the decisions, maintainer-facing.
- [packaging/verl/docs/verl-app-image-plan.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/verl/docs/verl-app-image-plan.md) — the implementation plan.
- [packaging/verl/docs/verl-hygon-e2e.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/verl/docs/verl-hygon-e2e.md) — the first backend E2E report.
