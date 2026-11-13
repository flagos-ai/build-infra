## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.48

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
- `gdb`
- `git`
- `libc6-dev-i386`
- `libncurses6`
- `libtinfo6`
- `make`
- `pciutils`
- `unzip`
- `vim`

### SDK components

- cnmon 6.5.48
- cntoolkit 4.7.2
- cncl 1.30.8
- cnclep 1.4.0
- cnnl 2.2.14
- cnnlextra 2.4.0
- mluops 1.12.0

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
  harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.7.2:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```

## Changelog

### 2.3.0

*2026-10-14 05:50:06*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:20:35*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-05 11:10:38*

- First delivery: Cambricon Neuware 4.7.2 — cntoolkit 4.7.2, cnnl 2.2.14,
  cnnlextra 2.4.0, mluops 1.12.0, cncl 1.30.8, cncv 2.12.1, cnclep 1.4.0 and
  cnmon 6.5.48 — on ubuntu:24.04, alongside the 4.4.3 line.
- `NEUWARE_HOME`, `PATH` and `LD_LIBRARY_PATH` are set in the image, so the
  toolkit is usable without an activation step.
