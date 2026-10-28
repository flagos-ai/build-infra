## Prerequisites

- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host driver:** 610.43.02
- **Container toolkit** *(optional)*: nvidia-container-toolkit

## Image contents

### Base image

`nvcr.io/nvidia/cuda:12.8.0-runtime-ubuntu24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `libelf1`
- `libnuma1` — 2.0.18
- `libpython3-dev` — 3.12.3
- `make` — 4.3
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- CUDA 12.8 (x86_64)

## Environment

- `PATH=/usr/local/nvidia/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`
- `LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64`
- `NVIDIA_VISIBLE_DEVICES=all`
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.3.0 bash
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
  harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
nvidia-smi
```

*Last updated: 2026-10-14 13:43:56 · `393cfb81d50e`*

## Changelog

### 2.3.0

*2026-10-14 05:50:15*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:20:34*

- The base layer is now only the apt install on top of the vendor image: our
  `/usr/local/cuda/bin` and `/usr/local/cuda/lib64` prepends are gone, as
  are the `NVIDIA_VISIBLE_DEVICES` and `NVIDIA_DRIVER_CAPABILITIES`
  redeclares. NGC already sets all four, so the prepends only duplicated
  entries in the effective `PATH` and `LD_LIBRARY_PATH` and the redeclares
  added nothing.

### 2.1.2

*2026-08-14 14:11:08*

- First delivery: the NGC CUDA 12.8.0 runtime image on ubuntu:24.04 with the
  build toolchain added — gcc/g++, cmake, make, libpython3-dev, curl, git,
  vim.
- NCCL comes from the vendor image, which preinstalls a held `libnccl2`, so
  this layer installs no collective library of its own.
