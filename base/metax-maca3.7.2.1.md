## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.8.30
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

- MetaX Driver 3.7.2.30
- MACA SDK 3.7.2.0

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
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```

## Changelog

### 2.3.0

*2026-10-14 05:50:03*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:20:45*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-14 15:00:10*

- First delivery: MACA 3.7.2.0 with driver 3.7.2.30 on ubuntu:24.04.
- The driver is installed in userspace mode only, so the image builds
  headless; the kernel driver stays on the host, as with NVIDIA.
- `MACA_PATH`, `PATH` and `LD_LIBRARY_PATH` are set in the image, so the
  toolkit is usable without an activation step.
