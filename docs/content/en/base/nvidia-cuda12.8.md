---
title: "nvidia-cuda12.8"
---

## Base image

`nvcr.io/nvidia/cuda:12.8.0-runtime-ubuntu24.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host driver:** 610.43.02
- **Container toolkit** *(optional — only for the toolkit launch below; the plain docker/podman command needs none)*: nvidia-container-toolkit

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

**With the container toolkit** *(optional)* (`nvidia-container-toolkit`):

```bash
docker run --rm -it --gpus all harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.1.1-19-ge0c6cbb bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it --device /dev/nvidia0 --device /dev/nvidiactl --device /dev/nvidia-uvm -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.1.1-19-ge0c6cbb bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
nvidia-smi
```
