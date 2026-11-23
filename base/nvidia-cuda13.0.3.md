## Prerequisites

- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host driver:** 610.43.02
- **Container toolkit** *(optional)*: nvidia-container-toolkit

## Image contents

### Base image

`nvcr.io/nvidia/cuda:13.0.3-runtime-ubuntu24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260816ubuntu0.24.04.2
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

- CUDA 13.0.3 (x86_64)

## Environment

- `PATH=/usr/local/nvidia/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`
- `LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64`
- `NVIDIA_VISIBLE_DEVICES=all`
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.0.3:2.3.0 bash
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
  harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.0.3:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
nvidia-smi
```

*Last updated: 2026-11-22 22:26:45 · `60f375b194d5`*

## Changelog

### 2.3.0

*2026-11-22 14:48:44*

- First delivery: the NGC CUDA 13.0.3 runtime image on ubuntu:24.04 with
  the build toolchain added.
- The toolkit major.minor is 13.0 rather than 13.3 so it matches what the
  cu130 wheels this stack installs (torch 2.13.0+cu130 and the
  third-party packages vLLM pulls in) were compiled against; CUDA
  minor-version compatibility only runs forward.
- `libnccl2=2.28.9-1+cuda13.0` is installed and held: the 13.x runtime
  images ship no NCCL, 2.28.9-1 is the newest build NVIDIA publishes for
  +cuda13.0, and the hold keeps an unpinned install downstream from
  moving it onto a later CUDA minor.
