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


{{< alert context="danger" >}}
🚧 **Under construction.** The Megatron app image is still being built and
validated. It is **not yet published** — the content below documents work in
progress, not a released product. Do not treat it as usable.
{{< /alert >}}

The **Megatron app image** is built on top of a `flagos-runtime` image and
packages a usable megatron-core library for megatron-lm based training.

## Build arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `RUNTIME_IMAGE` | _(required)_ | Runtime image ref, e.g. `harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2` |
| `MEGATRON_VERSION` | `0.17.1` | megatron-core version to install. A wheel of that version must exist on `FLAGOS_PYPI`. |
| `FLAGOS_PYPI` | `""` | Vendor PyPI index — hosts the megatron-core wheel. Searched first. |
| `EXTRA_PYPI` | `https://mirrors.aliyun.com/pypi/simple` | Aliyun mirror — fallback for all other dependencies. |

## megatron-core wheel

megatron-core's direct dependency surface is tiny (`torch>=2.6.0`, `numpy`,
`packaging>=24.2`) and the wheel keeps those declarations as-is — no repack,
no METADATA surgery. On every supported backend the runtime's vendor torch is
>= 2.7.1, which satisfies the `torch>=2.6.0` Requires-Dist, so pip resolves
nothing and overwrites nothing.

During `pip install`, the vendor PyPI is searched first — the wheel is found
and used. All remaining (safe) dependencies are resolved from `EXTRA_PYPI`.
Torch is already in the runtime venv and satisfies any transitive
constraints, so pip skips it. The install is a **single-step**
`pip install` (no `--no-deps`).

The wheel is built by `packaging/megatron/builder/` from the Megatron-LM-FL
fork — **inside the backend's own runtime image**, so build env == delivery
env and the single-step install is proven inert at build time (per-Python
cp310/cp311/cp312 wheels — the package ships a compiled `helpers_cpp`
extension; the fork's `requires-python >=3.12` is relaxed to `>=3.10` on the
fly at build time). See `packaging/megatron/builder/README.md`.

## Build example

```bash
docker build \
  --build-arg RUNTIME_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2 \
  --build-arg FLAGOS_PYPI=https://resource.flagos.net/repository/flagos-pypi-hygon/simple \
  -t harbor.baai.ac.cn/flagos-app/megatron-training-hygon-dtk26.04:2.1.2 \
  -f app/megatron/Containerfile.megatron-training .
# RL app: -f app/megatron/Containerfile.rl, tag megatron-rl-{vendor}-{backend}
```
