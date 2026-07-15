---
title: "metax-maca3.7.2.1"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.1.1`

Base image: `ubuntu:24.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550

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

- MetaX Driver 3.7.2.30
- MACA SDK 3.7.2.0

## Environment

- `PATH=/opt/maca/mxgpu_llvm/bin:/opt/maca/bin:${PATH}`
- `MACA_PATH=/opt/maca`
- `LD_LIBRARY_PATH=/opt/maca/lib:/opt/maca/mxgpu_llvm/lib`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --device /dev/mxcd --device /dev/dri --group-add video harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
mx-smi
```
