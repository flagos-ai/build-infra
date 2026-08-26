---
title: "enflame-tops1.10.6"
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
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.10.6
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: tencent-container-toolkit >= 2.0.52

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
- `make` — 4.3
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- Enflame driver 1.10.6
- TOPS Runtime 1.10.6
- TOPS CODEC 1.10.6
- TOPS CC 1.10.6
- TOPSTX 1.10.6
- TOPS PTI 1.10.6
- TOPS File 1.10.6
- TOPS Prof 1.10.6
- TOPS Sanitizer 1.10.6
- TOPS ATen 3.7.20260602
- EFML 1.10.6
- ECCL 3.6.3.11
- ECCL Tests 3.6.3.11
- Triton GCU 3.6.0+1.0.20260821.cc.1.10.6
- Gculare-perftest 1.10.6

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.10.6:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.10.6:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```

*Last updated: 2026-08-25 22:46:22 · `29d9b1e4e7c2`*
