---
title: "cambricon-neuware4.4.3"
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
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.2.15

## Image contents

### Base image

`ubuntu:22.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `gdb` — 12.1
- `git` — 2.34.1
- `libc6-dev-i386` — 2.35
- `libncurses5` — 6.3
- `libtinfo5` — 6.3
- `make` — 4.3
- `pciutils` — 3.7.0
- `unzip` — 6.0
- `vim` — 8.2.3995

### SDK components

- cnmon 6.2.15
- cntoolkit 4.4.3
- cncl 1.29.4
- cnclep 1.1.1.
- cnnl 2.1.829
- cnnlextra 2.2.7
- mluops 1.8.1

## Environment

- `NEUWARE_HOME=/usr/local/neuware`
- `PATH=/usr/local/neuware/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/neuware/lib64`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```

*Last updated: 2026-08-05 16:20:57 · `fbafbf2e5d9b`*
