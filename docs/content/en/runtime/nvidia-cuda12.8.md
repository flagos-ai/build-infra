---
title: "nvidia-cuda12.8"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host driver:** 610.43.02
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: nvidia-container-toolkit

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.1.1-30-gd767fb5`

### Python

3.12

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0`
- `torch==2.10.0+cu128`
- `torchaudio==2.10.0+cu128`
- `torchvision==0.25.0+cu128`
- <span class="muted"><code class="plain">triton==3.6.0</code></span>

<p class="muted"><em>Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).</em></p>

## Environment

- `NVIDIA_VISIBLE_DEVICES=all`
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it --gpus all flagos-runtime-nvidia-cuda12.8:latest bash
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
  flagos-runtime-nvidia-cuda12.8:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
nvidia-smi
```
