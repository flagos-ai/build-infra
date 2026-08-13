---
title: Megatron
weight: 20
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


The **Megatron app image** is built on top of a `flagos-runtime` image and
packages a usable megatron-core library for megatron-lm based training.

## Build arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `RUNTIME_IMAGE` | _(required)_ | Runtime image ref, e.g. `harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2` |
| `MEGATRON_VERSION` | `0.17.1` | megatron-core version to install. A repacked wheel (see below) must exist on `FLAGOS_PYPI`. |
| `FLAGOS_PYPI` | `""` | Vendor PyPI index — hosts the **repacked** megatron-core wheel. Searched first. |
| `EXTRA_PYPI` | `https://mirrors.aliyun.com/pypi/simple` | Aliyun mirror — fallback for all other dependencies. |

## Repacked megatron-core wheel

megatron-core's direct dependency surface is tiny (`torch>=2.6.0`, `numpy`,
`packaging>=24.2`) — and the only real risk is `torch`: on a backend whose
runtime torch is `< 2.6.0`, pip would pull public-PyPI torch over the vendor
build. We run `megatron-repack/` (reusing `vllm-repack/repack.py`) to strip
`Requires-Dist: torch` from the wheel's METADATA, then upload the repacked
wheel to the vendor's `FLAGOS_PYPI` with a `+flagos` version suffix.

During `pip install`, the vendor PyPI is searched first — the repacked wheel
is found and used. All remaining (safe) dependencies are resolved from
`EXTRA_PYPI`. Torch is already in the runtime venv and satisfies any
transitive constraints, so pip skips it. The install is a **single-step**
`pip install` (no `--no-deps`).

The wheel itself is built by `megatron-builder/` from the Megatron-LM-FL fork
(per-Python cp310/cp311/cp312 wheels — the package ships a compiled
`helpers_cpp` extension; the fork's `requires-python >=3.12` is relaxed to
`>=3.10` on the fly at build time). Classification rules live in
`megatron-repack/config.yaml`.

## Build example

```bash
docker build \
  --build-arg RUNTIME_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2 \
  --build-arg FLAGOS_PYPI=https://resource.flagos.net/repository/flagos-pypi-hygon/simple \
  -t harbor.baai.ac.cn/flagos-app/megatron-hygon-dtk26.04:2.1.2 \
  -f app/megatron/Containerfile .
```
