---
title: FlagGems
weight: 40
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


FlagGems is the operator library vLLM runs on in FlagOS images. It is shipped
three ways, split by the one fact that matters — the `flag_gems` package is
pure Python, the C++ operator library is not:

- **`flag_gems` wheel** — `py3-none-any`, so it needs no vendor toolchain and
  carries no glibc floor. One identical wheel is uploaded to every vendor PyPI.
- **`flag_gems_cpp_<backend>` wheel** — the per-backend C++ operators, built
  inside the runtime image (`{version}`), whose venv already has
  torch + deps + compilers. One per cmake backend, uploaded to that backend's
  vendor index.
- **`python3-flag-gems` `.deb`** — built from upstream's own `packaging/debian/`
  definition; build-infra owns only the release path.

## Why the python wheel needs no container

`py3-none-any` is platform-independent, so the build is a plain script:
clone FlagGems with tags, `pip wheel . --no-deps`, and a gate that fails loudly
unless the result is `py3-none-any` — a platform tag means the build hit the
C++ backend by mistake.

The version is FlagGems' own, read by `setuptools_scm` from its git tags. A
daily (non-tag) build stamps a throwaway local tag so `_version.py` still
carries the real commit, then the workflow uploads to `flagos-pypi-daily`.

## Why the cpp wheel builds in the runtime image

The C++ operators compile against torch and the vendor backend, so the build
environment has to equal the delivery environment — the same rule as the
vllm-plugin-FL native wheel. The runtime image (`{version}`) already
carries torch, the deps and the compilers, so
`pip wheel ./cpp` just works inside it.

Which backends get one is derived, not listed: `cpp_matrix.py` filters the
runtime matrix down to rows whose `configs.yaml` entry sets `cmake_backend`,
and `VENDOR_MAP` turns that into the wheel's name token (`cuda`, `npu`, `gcu`,
`ix`, `musa`).

## Why the deb lives upstream

The `packaging/debian/` definition is upstream's and stays there — that is
where distribution maintainers look for it. build-infra owns the *release
path* only (clone → build → verify → publish), so producing packages does not
depend on changes landing in the component repo. The package is
`Architecture: all`, so one artifact publishes into every apt suite.

## Full rationale

The design of record lives beside the code:

- [packaging/flaggems/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaggems/DESIGN.md) — the decisions, maintainer-facing.
- [packaging/flaggems/build.sh](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaggems/build.sh) — the python-wheel build.
- [scripts/release_flaggems.py](https://github.com/flagos-ai/build-infra/blob/main/scripts/release_flaggems.py) — the release path (build/upload/update-config).
- [scripts/cpp_matrix.py](https://github.com/flagos-ai/build-infra/blob/main/scripts/cpp_matrix.py) — which backends build a cpp wheel.
