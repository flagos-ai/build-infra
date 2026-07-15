---
title: "hygon-dtk26.04"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000

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

- Hygon DTK 26.04

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --device /dev/kfd --device /dev/dri --group-add video -v /opt/hyhal:/opt/hyhal --security-opt seccomp=unconfined harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
hy-smi
```
