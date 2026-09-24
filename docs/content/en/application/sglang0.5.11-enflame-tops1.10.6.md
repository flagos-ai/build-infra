---
title: "sglang0.5.11-enflame-tops1.10.6"
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
- **Host driver:** 1.9.10

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
| FlagTree | `0.7.0+triton3.6` (`3bc8649b`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `enflame`) |
| torch | 2.11.0 (torch_gcu 2.11.0) |

## Environment

- `TORCH_GCU_ENABLE_INT64_AND_UINT64=1`
- `ENABLE_I64_CHECK=0`
- `TORCHDYNAMO_DISABLE=1`
- `SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_IDLE=0`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_FLAGOS_BLACKLIST=isin,_unique2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-enflame-tops1.10.6:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-enflame-tops1.10.6:2.2.0-0.2.0
```

### Plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  -v /path/to/models:/models \
  $IMG bash
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  -v /path/to/models:/models \
  -e TOPS_VISIBLE_DEVICES=4,5,6,7 \
  -e TORCH_GCU_ENABLE_INT64_AND_UINT64=1 \
  -e ENABLE_I64_CHECK=0 \
  -e TORCHDYNAMO_DISABLE=1 \
  -e SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_IDLE=0 \
  -e FLAGCX_PATH=/sgl-workspace/FlagCX \
  -e SGLANG_FL_DIST_BACKEND=flagcx \
  -e SGLANG_FL_FLAGOS_BLACKLIST=isin,_unique2 \
  $IMG bash -c "python3 -m sglang.launch_server --model-path /models/Qwen3.6-27B --tp 4 --host 0.0.0.0 --port 30000 --trust-remote-code --mem-fraction-static 0.6 --disable-piecewise-cuda-graph --reasoning-parser qwen3 --attention-backend fa3"
```

This image ships no `sglang-serve` wrapper — start the server with `python3 -m sglang.launch_server` as shown above.
To limit which devices the container sees, set `TOPS_VISIBLE_DEVICES` to a comma-separated device list (as above); without it all GCU devices are used.

**Notes on the command above**

- ⚠️ **The launcher arguments must be wrapped in `bash -c "..."`.** The image's `ENTRYPOINT` is a vendor wrapper
  (`dev_entrypoint`) whose last step is `bash -c "$@"` — with more than one argument, only the **first word** is
  treated as the command string and the rest are silently dropped, so a bare
  `$IMG python3 -m sglang.launch_server --tp 4 ...` runs a plain `python3` with no arguments and the container exits
  immediately. Verified on the published image: `$IMG echo HELLO` prints nothing, while `$IMG bash -c "echo HELLO"` works.
- `--mem-fraction-static 0.6` is required on a Zixiao C200 (S60): each GCU reports only ~40.9 GiB usable, and `0.7` OOMs on a 27B model at `--tp 4`.
- The first launch of a freshly created container is slow — the FlagTree `enflame` backend compiles kernels on first use. Expect roughly 4 minutes of graph capture plus several minutes of warmup before `The server is fired up and ready to roll!`. This is CPU-bound compilation, not a hang.
- `SGLANG_FL_FLAGOS_BLACKLIST=isin,_unique2` makes `torch.isin` and `torch.unique` fall back to the vendor implementations. This is the vendor's documented configuration for this toolchain, not specific to this release.


