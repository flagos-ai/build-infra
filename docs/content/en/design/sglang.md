---
title: SGLang
weight: 70
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


The SGLang app images are the runtime image plus a **single-step
`pip install`** of a per-vendor wheel repacked from a self-built sdist. The
native wheel would clobber the runtime's torch matrix, so the line builds from
the **non-CUDA (`srt_empty`) variant**: its METADATA is torch-free and
`sgl-kernel`-free by construction, and repack only stamps the `+flagos` version
suffix.

## Why repack, not fork

Unlike Megatron — which builds a wheel from a fork whose torch requirement the
runtime satisfies — sglang has no such clean base: its CUDA variant pins
`torch==2.13.0` and a per-platform `sgl-kernel`. The `srt_empty` non-CUDA base
drops both, and `merge-runtime-base.py` folds in the pure-runtime closure, so
`pip install sglang==0.5.18+flagos` pulls the full runtime dependency set in one
step without touching torch or triton.

## Zero sgl-kernel

The install carries no native `sgl-kernel` wheel. A shared `sgl-kernel-shim`
satisfies the `sgl_kernel` import surface, and the hardware operators are all
provided by the runtime's flag_gems. The shim's symbols are never called — its
source lives in sglang-plugin-FL, not here.

## One sdist, many vendors

Every backend builds from the same sdist, inside its own runtime `-build`
image (ascend's aarch64 comes out of the aarch64 container). Per-vendor
differences — metax's JIT-gap fallbacks, for example — are host-side patches
applied before the build, or plugin-layer code, never baked into the wheel.

The `+flagos` suffix marks the wheel as ours so an exact pin never drifts to
the official `0.5.18`.

## Full rationale

The design of record lives beside the code:

- [packaging/sglang/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/sglang/DESIGN.md) — the decisions, maintainer-facing.
- [packaging/sglang/docs/sglang-0.5.18/decisions.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/sglang/docs/sglang-0.5.18/decisions.md) — the ADR record (§5.1–§5.8).
- [packaging/sglang/config.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/sglang/config.yaml) — the repack rules, as data.
