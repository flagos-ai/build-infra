---
title: "sglang0.5.11-generic-c13.0"
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
- **Chip models:** H800
- **Host driver:** 580.159.03

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
| FlagCX | `0.13.0` |
| triton | 3.6.0 |
| torch | 2.11.0 |

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-generic-c13.0:2.2.0-0.2.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-generic-c13.0:2.2.0-0.2.0
```

### Plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --gpus all \
  --ipc host \
  --shm-size=512g \
  -v /path/to/models:/models \
  $IMG bash
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --gpus all \
  --ipc host \
  --shm-size=512g \
  -v /path/to/models:/models \
  $IMG python3 -m sglang.launch_server --model-path /models/Qwen3.6-35B-A3B --tp 4 --host 0.0.0.0 --port 30000 --trust-remote-code
```

This image ships no default launcher command, and there is no `sglang-serve` wrapper in it — start the server with `python3 -m sglang.launch_server` as shown above. To limit which devices the container sees, pass `--gpus` with the device list in quotes, e.g. `--gpus '"device=4,5,6,7"'`.
