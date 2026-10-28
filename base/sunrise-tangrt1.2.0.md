## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1
- **Host driver:** 0.24.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `pciutils` — 3.10.0
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- Tang Toolkit 1.2.0
- PCCL 1.2.0
- taDNN 1.2.0
- taBLAS 1.2.0

## Environment

- `TANGRT_ROOT=/usr/local/tangrt`
- `LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`
- `LD_LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  -e TANG_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
pt_smi
```

*Last updated: 2026-10-14 13:43:56 · `393cfb81d50e`*

## Changelog

### 2.3.0

*2026-10-14 05:50:12*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:21:06*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-14 14:05:32*

- First delivery: TangRT 1.2.0 — the Tang toolkit, PCCL, taDNN and taBLAS —
  on ubuntu:24.04.
- `TANGRT_ROOT`, `LIBRARY_PATH` and `LD_LIBRARY_PATH` are set in the image,
  so the toolkit and its libraries resolve without an activation step.
