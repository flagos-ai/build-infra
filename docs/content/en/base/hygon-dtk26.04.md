---
title: "hygon-dtk26.04"
---

## Base image

`ubuntu:24.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host container toolkit:** dcu-container-toolkit >= 1.3.0

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

**Recommended** — with the container toolkit (`dcu-container-toolkit >= 1.3.0`):

```bash
docker run --rm -it -e DCU_VISIBLE_DEVICES=all harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1-16-gac22f59 bash
```

**Without the toolkit / podman** — raw device passthrough:

```bash
docker run --rm -it --device /dev/kfd --device /dev/mkfd --device /dev/dri --group-add video -v /opt/hyhal:/opt/hyhal --security-opt seccomp=unconfined harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1-16-gac22f59 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
source /opt/hyhal/env.sh && hy-smi
```
