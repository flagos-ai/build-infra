---
title: Megatron
weight: 60
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


The Megatron app images are the runtime image plus a **single-step
`pip install`** of a megatron-core wheel built from the
[Megatron-LM-FL](https://github.com/flagos-ai/Megatron-LM-FL) fork. Unlike
vLLM/SGLang — which repack an sdist to strip torch from its dependencies —
megatron is a **fork-source** path: the wheel keeps its `torch>=2.6.0`
requirement and the runtime's vendor torch satisfies it, so pip resolves
nothing and no dependency surgery is needed.

## Why the wheel is CPython-ABI-specific

megatron-core ships a compiled extension (`helpers_cpp`, pybind11), so every
wheel is `cp310` / `cp311` / `cp312` — never `py3-none-any` — and all three
must be built, because the runtime matrix uses all three Pythons. The extension
is declared `optional=True` upstream but imported unconditionally, so the build
gates on the `.so` being inside the wheel rather than trusting the compile.

## Build environment = the backend's runtime image

The wheel is built **inside the backend's own runtime image**, not a separate
builder image: the runtime carries the exact Python, torch and `pybind11==3.0.3`
the wheel will run against, so the ABI contracts match by construction and the
install is proven inert in the very image it ships in.

## One install, no `--no-deps`

The app install is `pip install "megatron-core[training|rl]==<version>"` — the
extra selects the scenario (`[training]` = modelopt/tqdm/datasets, `[rl]` =
GRPO). The pin carries the local label (`+fl.<date>.g<sha>`), because a bare
`0.17.1` would match every fork build of that version and pip would take the
highest one on the index. A `scipy<1.18` guard rides the same install to keep
modelopt from dragging numpy 2.0 over the runtime's numpy 1.26 pin.

## RL is paused

megatron_rl is paused (2026-08-31): the RL line moved to verl, and the Megatron
RL matrix column is ⏸. Only the training app is active here.

## Full rationale

The design of record lives beside the code:

- [packaging/megatron/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/megatron/DESIGN.md) — the decisions, maintainer-facing.
- [packaging/megatron/builder/README.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/megatron/builder/README.md) — how to run the wheel build.
- [packaging/megatron/docs/megatron-0.17.1/decisions.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/megatron/docs/megatron-0.17.1/decisions.md) — the ADR record (fork vs repack, helpers_cpp, no-deps, version format).
