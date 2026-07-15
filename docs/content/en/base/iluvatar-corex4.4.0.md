---
title: "iluvatar-corex4.4.0"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host container toolkit:** ix-container-toolkit >= 1.1.0

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `curl`
- `g++`
- `gcc`
- `unzip`

## SDK components

- Corex Runtime 4.4.0
- CUDA Header files 260604

## Environment

- `COREX_ROOT=/usr/local/corex`
- `PATH=/usr/local/corex/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/corex/lib`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --runtime iluvatar --env IX_VISIBLE_DEVICES=all harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
ixsmi
```
