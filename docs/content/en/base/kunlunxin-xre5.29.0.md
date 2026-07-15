---
title: "kunlunxin-xre5.29.0"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1`

Base image: `ubuntu:22.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `kmod` — 29
- `pciutils` — 3.7.0

## SDK components

- CUDA 12.9.0_575.51.03
- XRE-CUDA12 5.29.0.0
- XCUDART 5.13.0

## Environment

- `PATH=/usr/local/xpu/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/xpu/lib:/usr/local/xcudart/lib`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --device /dev/xpu0 --device /dev/xpuctrl harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
xpu-smi
```
