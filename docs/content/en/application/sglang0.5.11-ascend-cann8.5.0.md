---
title: "sglang0.5.11-ascend-cann8.5.0"
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
- **Chip models:** Ascend 910C
- **Host driver:** 25.5.0
- **Container toolkit:** Ascend-docker-runtime

## Image contents

### Python

3.11

### Application package

`sglang==0.5.11`


`sglang-fl==0.2.0`

### Component versions

| Component | Version |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.6.0+ascend3.2` |
| FlagCX | `0.13.0` |
| torch | 2.8.0 (torch_npu 2.8.0.post2) |
| CANN | 8.5.0 |

## Environment

- `ASCEND_RT_VISIBLE_DEVICES` — which devices the server uses, e.g. `0,1,2,3`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `HCCL_BUFFSIZE=1000`
- `HCCL_OP_EXPANSION_MODE=AIV`
- `STREAMS_PER_DEVICE=32`
- `SGLANG_ENABLE_OVERLAP_PLAN_STREAM=1`
- `SGLANG_NPU_USE_MULTI_STREAM=1`

The CANN and ATB environments must be sourced before launching:

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
```

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-ascend-cann8.5.0:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-ascend-cann8.5.0:2.2.0-0.2.0
```

This image ships no default entrypoint command, and there is no `sglang-serve` wrapper in it — start the server with `python3 -m sglang.launch_server` as shown below.

Start an interactive shell with the container toolkit:

```bash
docker run --rm -it \
  --runtime ascend \
  --privileged \
  --network host \
  --shm-size 32g \
  -e ASCEND_VISIBLE_DEVICES=0,1,2,3 \
  -v /path/to/models:/models \
  $IMG bash
```

Then, inside the container, source the environments and launch the server:

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh

export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export FLAGCX_PATH=/sgl-workspace/FlagCX
export HCCL_BUFFSIZE=1000
export HCCL_OP_EXPANSION_MODE=AIV
export STREAMS_PER_DEVICE=32
export SGLANG_ENABLE_OVERLAP_PLAN_STREAM=1
export SGLANG_NPU_USE_MULTI_STREAM=1

python3 -m sglang.launch_server \
  --model-path /models/Qwen3.6-35B-A3B --tokenizer-path /models/Qwen3.6-35B-A3B \
  --host 0.0.0.0 --port 30000 --tp 4 \
  --attention-backend ascend --device npu --dtype bfloat16 \
  --context-length 32768 --mem-fraction-static 0.8 \
  --cuda-graph-max-bs 60 --disable-radix-cache --trust-remote-code
```

Notes:

- `--tp` must match the number of devices you expose. Devices are selected with `ASCEND_VISIBLE_DEVICES` at `docker run` time and `ASCEND_RT_VISIBLE_DEVICES` inside the container.
- The server needs a large `/dev/shm`; a container created without `--shm-size` gets 64 MB and the server hangs during startup.
- The blacklist of FlagGems operators that are known not to compile or run on this stack is shipped **inside the image** (`sglang_fl/dispatch/config/ascend.yaml`); it is applied automatically, nothing has to be exported.
- For a thinking model (e.g. the Qwen3 family), add `--reasoning-parser qwen3` to separate the chain of thought into `reasoning_content`.
