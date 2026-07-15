---
title: "enflame-tops1.9.10"
---

Base image: `ubuntu:24.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0

## SDK components

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

Start an interactive shell in the container:

```bash
docker run --rm -it --device /dev/gcu harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
efsmi
```
