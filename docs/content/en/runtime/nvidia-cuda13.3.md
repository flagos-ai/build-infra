---
title: "nvidia-cuda13.3"
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
- **Chip models:** NVIDIA H20
- **Host driver:** 610.43.02
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: nvidia-container-toolkit

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.3:2.1.1`

### Python

3.12

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0`
- `torch==2.11.0+cu130`
- `torchaudio==2.11.0+cu130`
- `torchvision==0.26.0+cu130`
- <span class="muted"><code class="plain">triton==3.6.0</code></span>

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Environment

- `NVIDIA_VISIBLE_DEVICES=all`
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
nvidia-smi
```
