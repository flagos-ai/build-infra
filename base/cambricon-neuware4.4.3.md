## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.2.15

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
- `gdb` — 12.1
- `git` — 2.34.1
- `libc6-dev-i386` — 2.35
- `libncurses5` — 6.3
- `libtinfo5` — 6.3
- `make` — 4.3
- `pciutils` — 3.7.0
- `unzip` — 6.0
- `vim` — 8.2.3995

### SDK components

- cnmon 6.2.15
- cntoolkit 4.4.3
- cncl 1.29.4
- cnclep 1.1.1.
- cnnl 2.1.829
- cnnlextra 2.2.7
- mluops 1.8.1

## Environment

- `NEUWARE_HOME=/usr/local/neuware`
- `PATH=/usr/local/neuware/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/neuware/lib64`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```

*Last updated: 2026-10-14 13:43:56 · `393cfb81d50e`*

## Changelog

### 2.3.0

*2026-10-14 05:49:45*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:20:56*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-05 11:09:48*

- First delivery: Cambricon Neuware 4.4.3 — cntoolkit 4.4.3, cnnl 2.1.829,
  cnnlextra 2.2.7, mluops 1.8.1, cncl 1.29.4, cnclep 1.1.1 and cnmon 6.2.15
  — on ubuntu:22.04.
- This image stays on 22.04: `cnperf` needs `libncurses5`, which 24.04
  dropped.
- `NEUWARE_HOME`, `PATH` and `LD_LIBRARY_PATH` are set in the image, so the
  toolkit is usable without an activation step.
