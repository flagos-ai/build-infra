---
title: "sglang0.5.11-iluvatar-corex4.5.0"
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
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.5.0

## Image contents

### Python

3.12

### Application package

`sglang==0.5.11`


`sglang-fl==0.2.0`

### Component versions

| Component | Version |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`4819c190`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `iluvatar`) |
| torch | 2.10.0 |

## Environment

- `LD_LIBRARY_PATH` must be prefixed with `/usr/local/corex-host/lib64` — and keep the trailing `:$LD_LIBRARY_PATH`. Without it `torch.cuda.is_available()` silently returns `False` while `device_count()` still reports 16, because the corex runtime in the image does not match the host driver.
- `CUDA_VISIBLE_DEVICES` — device selection
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_PREFER=vendor`
- `SGLANG_FL_FLAGOS_BLACKLIST=max`
- `ATTENTION_BACKEND=triton`
- `NCCL_IB_DISABLE=1`
- `USE_FLAGTUNE=0` — FlagTune has no `corex` backend; leaving it enabled aborts startup

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-iluvatar-corex4.5.0:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-iluvatar-corex4.5.0:2.2.0-0.2.0
```

### Without a toolkit — plain docker / podman

This image ships no default application entrypoint command, so the launch command must be given explicitly.

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  --pid host \
  -v /dev:/dev \
  -v /lib/modules:/lib/modules \
  -v /sys:/sys \
  -v /usr/local/corex-4.5.0.20260509:/usr/local/corex-host \
  -v /path/to/models:/models \
  $IMG bash
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  --pid host \
  -v /dev:/dev \
  -v /lib/modules:/lib/modules \
  -v /sys:/sys \
  -v /usr/local/corex-4.5.0.20260509:/usr/local/corex-host \
  -v /path/to/models:/models \
  -e LD_LIBRARY_PATH=/usr/local/corex-host/lib64 \
  -e CUDA_VISIBLE_DEVICES=0,1,2,3 \
  $IMG python3 -m sglang.launch_server --model-path /models/Qwen3.6-27B --tp-size 4 --host 0.0.0.0 --port 30000
```

The devices are `/dev/iluvatar0` .. `/dev/iluvatar15` plus `/dev/itrctl` and `/dev/itrlink`; `-v /dev:/dev` exposes all of them. Selecting a subset works the same way with explicit `--device` flags, e.g. `--device /dev/iluvatar0 --device /dev/iluvatar1 --device /dev/itrctl`.

> The bind mount of the **host** corex directory (`/usr/local/corex-4.5.0.20260509` → `/usr/local/corex-host`) is required: the corex runtime bundled in the image does not match the host driver, so without it CUDA initialisation fails silently and the GPUs appear present but unusable. The path must match the corex version actually installed on the host.

> For a thinking model (e.g. the Qwen3 family), add `--reasoning-parser qwen3` — otherwise the chain of thought is not separated into `reasoning_content`.
