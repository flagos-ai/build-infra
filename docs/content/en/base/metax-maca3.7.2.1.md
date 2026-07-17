---
title: "metax-maca3.7.2.1"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.8.30
- **Container toolkit** <abbr title="only for the toolkit launch below; the plain docker/podman command needs none">*(optional)*</abbr>: metax-docker >= 0.15.3

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
- `libelf1`
- `libnuma1`
- `libpython3-dev`
- `make`

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
  --gpus all \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.1.1-20-g9ab46c9 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.1.1-20-g9ab46c9 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```
