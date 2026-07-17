---
title: "enflame-tops1.9.10"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.9.10
- **Container toolkit** <abbr title="only for the toolkit launch below; the plain docker/podman command needs none">*(optional)*</abbr>: tencent-container-toolkit >= 2.0.52

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

### SDK components

- Enflame driver 1.9.10
- TOPS Runtime 1.9.10
- TOPS CC 1.9.10
- TOPS PTI 1.9.10
- TOPSTX 1.9.10
- TOPS ATen 3.7.20260514
- EFML 1.9.10
- ECCL 3.6.3.11
- Triton GCU 3.6.0+1.0.20260521.cc.1.9.10
- Gculare-perftest 1.9.10

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.1-20-g9ab46c9 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/gcu \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.1-20-g9ab46c9 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```
