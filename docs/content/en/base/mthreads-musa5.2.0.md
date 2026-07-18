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
---
title: "mthreads-musa5.2.0"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

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
- `libelf1`
- `libgfortran5`
- `libnuma-dev`
- `libopenmpi-dev`
- `libpython3-dev`
- `openmpi-bin`

### SDK components

- MUSA Toolkits 5.2.0
- MCCL 2.4.0
- muDNN 3.4.0

## Environment

- `MUSA_HOME=/usr/local/musa`
- `PATH=/usr/local/musa/bin:${PATH}`
- `LD_LIBRARY_PATH=/usr/local/musa/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.1.1-31-g853fdf7 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.1.1-31-g853fdf7 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```
