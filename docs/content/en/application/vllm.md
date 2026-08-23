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

Ready-to-run images are published per backend — see the
[Application images]({{< relref "/application" >}}) catalog or the individual
per-backend pages for image references and launch commands.

## Build arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `RUNTIME_IMAGE` | _(required)_ | Runtime image ref, e.g. `harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.2` |
| `VLLM_VERSION` | `0.24.0` | vLLM version to install. A repacked `+flagos` wheel (see below) of that version must exist on `FLAGOS_PYPI`. |
| `FLAGOS_PYPI` | `""` | Vendor PyPI index — hosts the **repacked** vllm wheel. Searched first. |
| `EXTRA_PYPI` | `https://mirrors.aliyun.com/pypi/simple` | Aliyun mirror — fallback for all other dependencies. |
| `PLUGIN_FL_VERSION` | `""` | vllm-plugin-FL wheel version (commit-precise), e.g. `0.2.0+gcf8998c.d20260815`. Installed from the vendor PyPI; empty = plugin not installed. A non-empty value appends `-{version}` (`+` → `_`) to the image tag. |
| `APP_DEPS` | `""` | Vendor-conditional packages for this app (configs.yaml `deps_app.vllm`), space-separated, installed from the vendor PyPI. |

## Repacked vLLM wheel

The official vLLM wheel declares `Requires-Dist` on torch, triton, and
CUDA-only packages that would overwrite the carefully curated stack in the
runtime image. We run `packaging/vllm/repack.py` to surgically strip these
entries from the wheel's METADATA, then upload the repacked wheel to the
vendor's `FLAGOS_PYPI` as `vllm-{version}+flagos`.

During `pip install`, the vendor PyPI is searched first — the repacked
wheel is found and used. All remaining (safe) dependencies are resolved
from `EXTRA_PYPI`. Torch and triton are already in the runtime venv and
satisfy any transitive constraints, so pip skips them. The `+flagos` marker
is pinned explicitly in the build (`vllm==${VLLM_VERSION}+flagos`) — a bare
`vllm=={version}` would resolve to the official wheel, whose torch
Requires-Dist would overwrite the pinned vendor torch.

See `packaging/vllm/repack.py` for the repacking tool and
`packaging/vllm/config.yaml` for the classification rules.

## vllm-plugin-FL

The plugin is installed as a prebuilt wheel (`vllm-plugin-fl==<version>`)
from the vendor PyPI — no source build inside the app image. The wheel is
built and dependency-audited by the vllm-plugin-wheel workflow. The
`PLUGIN_FL_VERSION` build arg pins the exact version; when it is non-empty,
the published image tag gains a `-{version}` segment (`+` → `_`), e.g.
`vllm0.24.0-nvidia-cuda12.8:2.1.2-0.2.0_gcf8998c.d20260815`.

## Build example

```bash
docker build \
  --build-arg RUNTIME_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.2 \
  --build-arg FLAGOS_PYPI=https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --build-arg PLUGIN_FL_VERSION=0.2.0+gcf8998c.d20260815 \
  -t harbor.baai.ac.cn/flagos-app/vllm0.24.0-nvidia-cuda12.8:2.1.2-0.2.0_gcf8998c.d20260815 \
  -f app/vllm/Containerfile .
```
