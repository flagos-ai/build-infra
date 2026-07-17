---
title: "kunlunxin-xre5.29.0"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.29.0.0
- **Container toolkit** *(optional — only for the toolkit launch below; the plain docker/podman command needs none)*: xpu_container >= 1.0.13

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
- `kmod`
- `pciutils`

### SDK components

- CUDA 12.9.0_575.51.03
- XRE-CUDA12 5.29.0.0
- XCUDART 5.13.0

## Environment

- `PATH=/usr/local/xpu/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/xpu/lib:/usr/local/xcudart/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1-17-g361735c bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1-17-g361735c bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
xpu-smi
```
