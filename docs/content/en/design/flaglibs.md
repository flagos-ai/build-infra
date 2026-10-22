---
title: FlagLibs
weight: 50
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


FlagLibs publishes the FlagOS **operator libraries** (FlagAttention, FlagSparse,
FlagBLAS, FlagAudio, FlagFFT, FlagGems-vllm, FlagGems-sglang) as installable
wheels. Every one of them is pure Python, which shapes the whole line: the
wheels are `py3-none-any`, so there is no vendor toolchain, no container and no
glibc floor — a plain venv script builds all of them.

## Why one hosted index, not per-vendor

The per-vendor indexes (`flagos-pypi-<vendor>`) exist to separate
vendor-bound binaries — wheels that link a specific toolchain, like
`flag_gems_cpp` or `torch_musa`. These libraries carry no device binary
(Triton JIT provides the backend adaptation at run time), so a single publish
to `flagos-pypi-hosted` serves every vendor's runtime.

## Version is the build ref

Each wheel's version is a pure function of the ref it is built from: the
upstream release tag (`v0.4.0` → `0.4.0`). build-infra synthesizes no version
number — unlike the flagcx wheel's `+<backend>` local label, which exists to
tell two vendors' builds of one commit apart. Here there is only one wheel per
library, so the tag alone is enough.

One library, `flag_attn`, is versioned by `setuptools_scm` from its git tags
and so needs a full clone with tags (a shallow clone degrades to `0.0.0`); the
rest carry a static pyproject version and a shallow tag checkout suffices.

## Build only in CI

The build script runs locally for a dry-run, but publishing happens only in
GitHub Actions (`flaglibs-wheel.yml`, manual dispatch, gated by
`check-trigger-author`) — the same discipline as flagtree and flaggems.

## Full rationale

The design of record lives beside the code:

- [packaging/flaglibs/docs/decisions.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaglibs/docs/decisions.md) — the decision record (D1–D7).
- [packaging/flaglibs/build-config.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaglibs/build-config.yaml) — the library list: repo, default ref, version source.
- [packaging/flaglibs/build.sh](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaglibs/build.sh) — the build.
