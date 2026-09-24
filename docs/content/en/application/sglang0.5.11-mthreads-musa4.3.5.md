---
title: "sglang0.5.11-mthreads-musa4.3.5"
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
- **Chip models:** MTT S5000
- **Host driver:** 3.3.5-server (`musa` driver package)
- **Container toolkit:** MUSA 4.3.5 (bundled in the image)

## Image contents

### Python

3.10

### Application package

`sglang==0.5.11`


`sglang-fl==0.2.0`

### Component versions

| Component | Version |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`4819c19`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `mthreads`) |
| torch | 2.9.0 (torch_musa 2.9.0) |

## Environment

- `source /root/.virtualenvs/sglang-0.5.6/bin/activate` — **required**. sglang and the FlagOS components live in this virtualenv; without activating it, `python3` resolves to the base image's older `flag_gems` / `sglang_fl`.
- `MUSA_VISIBLE_DEVICES` — device selection, e.g. `0,1,2,3`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_MUSA_FP32_TP_ALLREDUCE=1`
- `MCCL_SOCKET_IFNAME=bond0` and `GLOO_SOCKET_IFNAME=bond0` — the NIC used for multi-GPU communication
- `MCCL_TIMEOUT=14400`
- `TORCH_COMPILE_DISABLE=1` — the FlagTree `mthreads` triton spec shadows the stock triton, so `torch.compile` fails at import time
- `SGLANG_FL_PER_OP=topk=reference`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-mthreads-musa4.3.5:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-mthreads-musa4.3.5:2.2.0-0.2.0
```

### Without a toolkit — plain docker / podman

This image ships no default entrypoint command, so the launch command must be given explicitly.

Start an interactive shell (`--privileged` is required for MUSA device access):

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  --shm-size 512g \
  -e MTHREADS_VISIBLE_DEVICES=all \
  -v <model-dir>:/models \
  $IMG bash
```

Then, inside the container, start the server with `tp=4`:

```bash
source /root/.virtualenvs/sglang-0.5.6/bin/activate
export MUSA_VISIBLE_DEVICES=0,1,2,3
export FLAGCX_PATH=/sgl-workspace/FlagCX
export SGLANG_FL_DIST_BACKEND=flagcx
export SGLANG_MUSA_FP32_TP_ALLREDUCE=1
export SGLANG_FL_PER_OP=topk=reference
export MCCL_SOCKET_IFNAME=bond0
export GLOO_SOCKET_IFNAME=bond0
export MCCL_TIMEOUT=14400
export TORCH_COMPILE_DISABLE=1
python3 -m sglang.launch_server --model-path /models/<model> --host 0.0.0.0 --port 30000 \
  --tp-size 4 --page-size 64 --disable-piecewise-cuda-graph --disable-radix-cache \
  --trust-remote-code --mem-fraction-static 0.75 --reasoning-parser qwen3 --cuda-graph-max-bs 32
```

> For a thinking model (e.g. the Qwen3 family), `--reasoning-parser qwen3` is required — otherwise the chain of thought is not separated into `reasoning_content`.
