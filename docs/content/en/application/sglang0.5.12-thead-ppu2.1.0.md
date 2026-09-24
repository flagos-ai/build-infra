---
title: "sglang0.5.12-thead-ppu2.1.0"
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
- **Chip models:** T-Head PPU-ZW810E
- **Host driver:** 1.3.2-d7f5a2

## Image contents

### Python

3.12

### Application package

`sglang==0.5.12+v0.1.0.ppu2.1.0`


`sglang-fl==0.2.0`

### Component versions

| Component | Version |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`3bc8649b`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `ppu`) |
| torch | 2.10.0 |

## Environment

- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_FLAGOS_BLACKLIST=count_nonzero,cumsum`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.12-thead-ppu2.1.0:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.12-thead-ppu2.1.0:2.2.0-0.2.0
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  --shm-size=512g \
  --ipc host \
  --network host \
  -v /dev:/dev \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --privileged \
  --shm-size=512g \
  --ipc host \
  --network host \
  -v /dev:/dev \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  --shm-size=512g \
  --ipc host \
  --network host \
  -v /dev:/dev \
  $IMG python3 -m sglang.launch_server --model-path <path> --port 30000
```

The devices are the PPU SDK nodes (`/dev/alixpu`, `/dev/alixpu_ctl`, `/dev/alixpu_ppu0..15`); `-v /dev:/dev` exposes all of them. Selecting a subset works the same way with explicit `--device` flags, e.g. `--device /dev/alixpu --device /dev/alixpu_ctl --device /dev/alixpu_ppu0 --device /dev/alixpu_ppu1`.

