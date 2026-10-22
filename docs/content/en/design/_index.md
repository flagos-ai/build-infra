---
title: Design
weight: 55
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


The decisions behind how FlagOS builds and packages things — *why* a wheel is
labelled a certain way or a build is shaped a certain way, not just *what* it
produces.

These pages are short, operator-facing summaries. The full rationale lives
beside the code it describes (a `DESIGN.md` in the relevant `packaging/` or
`docs/` directory); each page links to it. The record of truth is the in-repo
file, not this site.

- **[vllm-plugin-FL]({{< relref "vllm-plugin-fl" >}})** — the native `vllm_fl._C`
  wheel, its bare-backend label scheme, and why it builds inside the runtime
  image instead of a builder image.
- **[FlagTree]({{< relref "flagtree" >}})** — the source-built per-backend
  compiler wheels, the `--target builder` split, and the daily line.
- **[FlagCX]({{< relref "flagcx" >}})** — the collective-communication library's
  deb/wheel/builder channels, the one-artifact-per-backend rule, and the
  glibc floor.
- **[FlagGems]({{< relref "flaggems" >}})** — the pure-Python `flag_gems` wheel,
  the per-backend cpp wheel, and the upstream-owned deb.
- **[FlagLibs]({{< relref "flaglibs" >}})** — the operator libraries, one
  `py3-none-any` wheel per library on a single hosted index.
- **[Megatron]({{< relref "megatron" >}})** — the fork-source wheel, built in
  the backend's runtime image and installed single-step with no `--no-deps`.
- **[SGLang]({{< relref "sglang" >}})** — the repacked `srt_empty` wheel, the
  `+flagos` suffix, and the zero-sgl-kernel route.
- **[verl]({{< relref "verl" >}})** — the fork-source RL-training wheel, one
  `py3-none-any` for all backends, with megatron-core + vllm riding on the
  runtime's existing matrix.
