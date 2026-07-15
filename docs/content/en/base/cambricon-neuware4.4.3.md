---
title: "cambricon-neuware4.4.3"
---

Base image: `ubuntu:22.04`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `gdb` — 12.1
- `libc6-dev-i386` — 2.35
- `libncurses5` — 6.3
- `libtinfo5` — 6.3
- `make` — 4.3
- `pciutils` — 3.7.0
- `unzip` — 6.0

## SDK components

- cndev 6.5.25 (amd64)
- cnmon 6.2.15
- cnbin 2.4.2
- cndrv 3.4.3
- cnrt 7.4.0
- cnrtc 0.7.4
- cncc/cnas 5.4.3
- cngdb 4.4.2
- cnpapi 4.4.2
- cnpx 1.6.0
- cnperf 6.4.3
- cnjpeg 0.5.1
- cncodec3 2.4.1
- cnsanitizer 0.12.3
- cnnl+extra 2.1.829
- mluops 1.8.1
- cncl 1.29.4
- cnstudio 1.2.1
- cntoolkit 4.4.3
- cntoolkit-cloud 4.4.3
- cnclep 1.1.1.

## Environment

- `PATH=/usr/local/neuware/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/neuware/lib64`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --device /dev/cambricon_dev0 --device /dev/cambricon_ctl -v /usr/bin/cnmon:/usr/bin/cnmon harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
cnmon
```
