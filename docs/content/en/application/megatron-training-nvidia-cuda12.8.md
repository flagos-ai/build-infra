---
title: "megatron-training-nvidia-cuda12.8"
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

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.2</code> <a href="../../runtime/nvidia-cuda12.8/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f`

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f megatron-train --model-type GPT
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
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f megatron-train --model-type GPT
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
nvidia-smi
```
