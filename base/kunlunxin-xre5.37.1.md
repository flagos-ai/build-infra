*Last updated: 2026-08-05 16:20:57 · `fbafbf2e5d9b`*

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.37.1
- **Container toolkit** *(optional)*: xpu_container >= 1.0.13

## Image contents

### Base image

`ubuntu:22.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `git` — 2.34.1
- `make` — 4.3
- `pciutils` — 3.7.0
- `vim` — 8.2.3995

### SDK components

- CUDA 12.9.0_575.51.03
- XRE-CUDA12 5.37.1.0
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
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.37.1:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.37.1:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
xpu-smi
```
