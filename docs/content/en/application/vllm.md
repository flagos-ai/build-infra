---
title: vLLM
weight: 10
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


The **vLLM app image** is built on top of a `flagos-runtime` image and
packages a ready-to-run vLLM server with vllm-plugin-FL.

## Build arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `RUNTIME_IMAGE` | _(required)_ | Runtime image ref, e.g. `harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.1` |
| `VLLM_VERSION` | `0.20.2` | vLLM version to install. A repacked wheel (see below) must exist on `FLAGOS_PYPI`. |
| `FLAGOS_PYPI` | `""` | Vendor PyPI index — hosts the **repacked** vllm wheel. Searched first. |
| `EXTRA_PYPI` | `https://mirrors.aliyun.com/pypi/simple` | Aliyun mirror — fallback for all other dependencies. |
| `PLUGIN_FL_REF` | `""` | vllm-plugin-FL git ref (tag, branch, or commit). |
| `VLLM_VENDOR` | `cuda` | Vendor identifier for C++ extension compilation. `cuda` for CUDA-ABI backends; `ascend` / `gcu` for PrivateUse1. |

## Repacked vLLM wheel

The official vLLM wheel declares `Requires-Dist` on torch, triton, and
CUDA-only packages that would overwrite the carefully curated stack in the
runtime image. We run `vllm-repack/repack.py` to surgically strip these
entries from the wheel's METADATA, then upload the repacked wheel to the
vendor's `FLAGOS_PYPI` at the same version.

During `pip install`, the vendor PyPI is searched first — the repacked
wheel is found and used. All remaining (safe) dependencies are resolved
from `EXTRA_PYPI`. Torch and triton are already in the runtime venv and
satisfy any transitive constraints, so pip skips them.

See `vllm-repack/repack.py` for the repacking tool and
`vllm-repack/config.yaml` for the classification rules.

## vllm-plugin-FL

The plugin is currently installed from source (no release wheel yet).
The `PLUGIN_FL_REF` build arg pins the exact git ref. The `VLLM_VENDOR`
arg controls which C++ backend is compiled.

> **TODO:** Build and publish `vllm-plugin-FL` wheels per vendor. Once
> available, the Containerfile will switch to `pip install` from wheel
> instead of source-building.

## Build example

```bash
docker build \
  --build-arg RUNTIME_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.1 \
  --build-arg FLAGOS_PYPI=https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --build-arg PLUGIN_FL_REF=main \
  -t harbor.baai.ac.cn/flagos-app/vllm-nvidia-cuda12.8:2.1.1 \
  -f app/vllm/Containerfile .
```
