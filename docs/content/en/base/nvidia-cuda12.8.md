---
title: "nvidia-cuda12.8"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.1.1`

## Prerequisites

- **Operating system:** `nvcr.io/nvidia/cuda:12.8.0-runtime-ubuntu24.04`
- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host container toolkit:** nvidia-container-toolkit

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `libelf1`
- `libnuma1` — 2.0.18
- `libpython3-dev` — 3.12.3
- `make` — 4.3

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
