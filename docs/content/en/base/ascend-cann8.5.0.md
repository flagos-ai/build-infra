---
title: "ascend-cann8.5.0"
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

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 25.5.0
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `libelf1`
- `libpython3-dev` — 3.12.3
- `make` — 4.3
- `net-tools` — 2.10
- `pciutils` — 3.10.0
- `python3-pip` — 24.0+dfsg
- `python3.11` — 3.11.15
- `python3.11-dev` — 3.11.15
- `software-properties-common` — 0.99.49.4
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- CANN Toolkit 8.5.0 (aarch64)
- CANN 910B Ops 8.5.0 (aarch64)
- CANN NNAL 8.5.0 (aarch64)

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
npu-smi info
```

*Last updated: 2026-08-11 01:04:24 · `3eca2bf66bfc`*
