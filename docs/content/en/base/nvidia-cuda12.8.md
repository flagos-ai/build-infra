---
title: "nvidia-cuda12.8"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.1.1`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host container toolkit:** nvidia-container-toolkit

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `libelf1`
- `libnuma1`
- `libpython3-dev`
- `make`

## SDK components

- CUDA 12.8 (x86_64)

## Environment

- `PATH=/usr/local/cuda/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --gpus all harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
nvidia-smi
```
