---
title: "kunlunxin-xre5.29.0"
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

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.29.0.0
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: xpu_container >= 1.0.13

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `kmod`
- `pciutils`

### SDK components

- CUDA 12.9.0_575.51.03
- XRE-CUDA12 5.29.0.0
- XCUDART 5.13.0

## Environment

- `PATH=/usr/local/xpu/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/xpu/lib:/usr/local/xcudart/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
xpu-smi
```
