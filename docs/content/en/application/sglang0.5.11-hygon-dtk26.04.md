---
title: "sglang0.5.11-hygon-dtk26.04"
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
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a

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
| FlagTree | `0.7.0+triton3.6` (`3bc8649b`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `hcu`) |
| torch | 2.10.0 |

## Environment

- `LD_LIBRARY_PATH` must additionally contain `/usr/local/lib/python3.10/dist-packages/torch/lib:/opt/dtk/cuda/cuda-12/lib64`, otherwise FlagCX fails to load with `libcudart.so.12: cannot open shared object file`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_FLAGOS_BLACKLIST=cumsum,layer_norm`
- `SGLANG_FL_PREFER=vendor`
- `SGLANG_FL_STRICT=1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-hygon-dtk26.04:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-hygon-dtk26.04:2.2.0-0.2.0
```

### Without a toolkit — plain docker / podman

This image ships no default entrypoint command, so the launch command must be given explicitly.

Start an interactive shell:

```bash
docker run --rm -it \
  --network host \
  --ipc host \
  --privileged \
  --group-add video \
  --cap-add SYS_PTRACE \
  --security-opt seccomp=unconfined \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  -v /opt/hyhal:/opt/hyhal:ro \
  -e HIP_VISIBLE_DEVICES=0,1 \
  -e CUDA_VISIBLE_DEVICES=0,1 \
  $IMG bash
```

⚠️ Device selection must be pinned at `docker run -e` time (the `HIP_VISIBLE_DEVICES` / `CUDA_VISIBLE_DEVICES` above); exporting them later inside the container makes device enumeration hang.

Then, inside the container, start the server with `tp=2`:

```bash
source /opt/dtk/env.sh
export LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/torch/lib:/opt/dtk/cuda/cuda-12/lib64:$LD_LIBRARY_PATH
export FLAGCX_PATH=/sgl-workspace/FlagCX
export SGLANG_FL_DIST_BACKEND=flagcx
export SGLANG_FL_FLAGOS_BLACKLIST=cumsum,layer_norm
export SGLANG_FL_PREFER=vendor
export SGLANG_FL_STRICT=1
python3 -m sglang.launch_server --model-path <path> --host 0.0.0.0 --port 30000 --tp 2 --page-size 64 --disable-radix-cache --context-length 262144 --mem-fraction-static 0.80 --chunked-prefill-size 4096 --max-running-requests 64 --trust-remote-code --disable-piecewise-cuda-graph --reasoning-parser qwen3
```

> For a thinking model (e.g. the Qwen3 family), `--reasoning-parser qwen3` is required — otherwise the chain of thought is not separated into `reasoning_content`.
