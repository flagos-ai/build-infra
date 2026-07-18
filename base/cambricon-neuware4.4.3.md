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

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `gdb`
- `libc6-dev-i386`
- `libncurses6`
- `libtinfo6`
- `make`
- `pciutils`
- `unzip`

### SDK components

- cndev 6.5.25 (amd64)
- cnmon 6.2.15
- cnbin 2.4.2
- cndrv 3.4.3
- cnrt 7.4.0
- cnrtc 0.7.4
- cncc/cnas 5.4.3
- cngdb 4.4.2
- cnpapi 4.4.2
- cnpx 1.6.0
- cnperf 6.4.3
- cnjpeg 0.5.1
- cncodec3 2.4.1
- cnsanitizer 0.12.3
- cnnl+extra 2.1.829
- mluops 1.8.1
- cncl 1.29.4
- cnstudio 1.2.1
- cntoolkit 4.4.3
- cntoolkit-cloud 4.4.3
- cnclep 1.1.1.

## Environment

- `PATH=/usr/local/neuware/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/neuware/lib64`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.1.1-21-g7fe5cbd bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```
