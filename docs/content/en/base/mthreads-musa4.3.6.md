---
title: "mthreads-musa4.3.6"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

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
- `libgfortran5`
- `libnuma-dev`
- `libopenmpi-dev`
- `libpython3-dev`
- `openmpi-bin`

### SDK components

- MUSA Toolkits RC4.3.6
- MCCL RC2.1.6
- muDNN RC3.1.6

## Environment

- `MUSA_HOME=/usr/local/musa`
- `PATH=/usr/local/musa/bin:${PATH}`
- `LD_LIBRARY_PATH=/usr/local/musa/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa4.3.6:2.1.1-30-gd767fb5 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa4.3.6:2.1.1-30-gd767fb5 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```
