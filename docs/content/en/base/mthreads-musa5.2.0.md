---
title: "mthreads-musa5.2.0"
---

## Base image

`ubuntu:24.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host container toolkit:** KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## System packages

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

## SDK components

- MUSA Toolkits 5.2.0
- MCCL 2.4.0
- muDNN 3.4.0

## Environment

- `MUSA_HOME=/usr/local/musa`
- `PATH=/usr/local/musa/bin:${PATH}`
- `LD_LIBRARY_PATH=/usr/local/musa/lib`

## Launch

Launch with the container toolkit (`KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0`):

```bash
docker run --rm -it --runtime mthreads --env MTHREADS_VISIBLE_DEVICES=all harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.1.1-16-gac22f59 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
mthreads-gmi
```
