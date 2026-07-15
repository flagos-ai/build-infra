---
title: "hygon-dtk26.04"
---

## Base image

`ubuntu:22.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `pciutils` — 3.7.0

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
