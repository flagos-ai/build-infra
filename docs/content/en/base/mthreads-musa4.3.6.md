---
title: "mthreads-musa4.3.6"
---

## Base image

`ubuntu:22.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host container toolkit:** KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `libelf1` — 0.186
- `libgfortran5` — 12.3.0
- `libnuma-dev` — 2.0.14
- `libopenmpi-dev` — 4.1.2
- `libpython3-dev` — 3.10.6
- `openmpi-bin` — 4.1.2

## SDK components

- MUSA Toolkits RC4.3.6
- MCCL RC2.1.6
- muDNN RC3.1.6

## Environment

- `MUSA_HOME=/usr/local/musa`
- `PATH=/usr/local/musa/bin:${PATH}`
- `LD_LIBRARY_PATH=/usr/local/musa/lib`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --runtime mthreads --env MTHREADS_VISIBLE_DEVICES=all harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa4.3.6:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
mthreads-gmi
```
