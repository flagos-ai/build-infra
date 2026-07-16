---
title: "sunrise-tangrt1.2.0"
---

## Base image

`ubuntu:24.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `pciutils`

## SDK components

- Tang Toolkit 1.2.0
- PCCL 1.2.0
- taDNN 1.2.0
- taBLAS 1.2.0

## Environment

- `TANGRT_ROOT=/usr/local/tangrt`
- `LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`
- `LD_LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1-16-gac22f59 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
pt_smi
```
