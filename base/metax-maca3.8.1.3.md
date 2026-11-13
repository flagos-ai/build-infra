## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.9.6
- **Container toolkit** *(optional)*: metax-docker >= 0.15.3

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `git`
- `libelf1`
- `libnuma1`
- `libpython3-dev`
- `make`
- `unzip`
- `vim`

### SDK components

- MetaX Driver 3.8.1.6
- MACA SDK 3.8.1.3

## Environment

- `PATH=/opt/maca/mxgpu_llvm/bin:/opt/maca/bin:${PATH}`
- `MACA_PATH=/opt/maca`
- `LD_LIBRARY_PATH=/opt/maca/lib:/opt/maca/mxgpu_llvm/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.8.1.3:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.8.1.3:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```

## Changelog

### 2.3.0

*2026-10-14 05:49:44*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:44:47*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-14 15:04:10*

- First delivery: MACA 3.8.1.3 with driver 3.8.1.6 on ubuntu:24.04,
  alongside the 3.7.2.1 line.
- The driver is installed in userspace mode only, so the image builds
  headless; the kernel driver stays on the host, as with NVIDIA.
- `MACA_PATH`, `PATH` and `LD_LIBRARY_PATH` are set in the image, so the
  toolkit is usable without an activation step.
