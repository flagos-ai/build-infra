---
title: "sglang0.5.12-kunlunxin-xre5.37.1"
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
- **Chip models:** KunlunXin P800 OAM (96 GiB per card)
- **Host driver:** 5.37.1.0

## Image contents

### Python

3.10.12

### Application package

`sglang==0.5.12`

`sglang-fl==0.2.0`

### Component versions

| Component | Version |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`4819c190`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `xpu`) |
| torch | 2.9.0 (torch_xmlir `XMLIR-v2.9.0`, XRE 5.35.0.0 / XCCL 3.1.9.0) |

## Environment

- `SGLANG_FL_CONFIG=/sgl-workspace/sglang-plugin-FL/sglang_fl/dispatch/config/kunlunxin.yaml` (**required**, see below)
- `XPU_VISIBLE_DEVICES=0,1,2,3` (set `CUDA_VISIBLE_DEVICES` to the same value — both are needed)
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `USE_FLAGGEMS=1`
- `USE_FLAGTUNE=0`
- `MM_ATTENTION_BACKEND=sdpa`

> ⚠️ **`SGLANG_FL_CONFIG` is required, not optional.** Without it the plugin auto-detects the
> platform, and on this stack the detection resolves to `nvidia` (`torch.cuda.is_available()`
> is true), so it loads the empty `config/nvidia.yaml` — **none of the 43 built-in operator
> blacklist entries take effect and the server will not come up.**
>
> ⚠️ That blacklist is itself what makes this image runnable: the XPU compiler still has two
> unfixed defects in this release (a degraded `tl.exp2` and a `cmpf` type error under
> compare-fusion), and the blacklist routes those operators back to their native
> implementations.

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.12-kunlunxin-xre5.37.1:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.12-kunlunxin-xre5.37.1:2.2.0-0.2.0
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  --network host \
  --shm-size=512g \
  -v /public-flash/models:/models \
  $IMG bash
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  --network host \
  --shm-size=512g \
  -v /public-flash/models:/models \
  -e SGLANG_FL_CONFIG=/sgl-workspace/sglang-plugin-FL/sglang_fl/dispatch/config/kunlunxin.yaml \
  -e FLAGCX_PATH=/sgl-workspace/FlagCX \
  -e USE_FLAGGEMS=1 \
  -e USE_FLAGTUNE=0 \
  -e MM_ATTENTION_BACKEND=sdpa \
  $IMG python3 -m sglang.launch_server --model-path <path> --tp-size 4 --host 0.0.0.0 --port 30000 --page-size 1 --mem-fraction-static 0.75 --watchdog-timeout 3600 --attention-backend kunlunxin --disable-piecewise-cuda-graph --cuda-graph-max-bs 60 --sampling-backend pytorch --mm-attention-backend sdpa --reasoning-parser qwen3 --trust-remote-code
```

> ⚠️ The `-e SGLANG_FL_CONFIG=…` above is **not optional** (see the Environment section);
> in the interactive-shell form above you would export it inside the container instead.

The devices are the KunlunXin XPU nodes; `--privileged` exposes all of them. Selecting a subset
works with `XPU_VISIBLE_DEVICES` **and** `CUDA_VISIBLE_DEVICES` (set both, also via `-e`), e.g.
`-e XPU_VISIBLE_DEVICES=4,5,6,7 -e CUDA_VISIBLE_DEVICES=4,5,6,7`.
