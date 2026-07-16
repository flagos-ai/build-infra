---
title: "iluvatar-corex4.4.0"
---

## Base image

`ubuntu:24.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional — only for the toolkit launch below; the plain docker/podman command needs none)*: ix-container-toolkit >= 1.1.0

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

**With the container toolkit** *(optional)* (`ix-container-toolkit >= 1.1.0`):

```bash
docker run --rm -it --runtime iluvatar --env IX_VISIBLE_DEVICES=all harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1-19-ge0c6cbb bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it --device /dev/iluvatar0 -v /usr/local/corex:/usr/local/corex:ro harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1-19-ge0c6cbb bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
ixsmi
```
