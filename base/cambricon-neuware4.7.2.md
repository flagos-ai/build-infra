*Last updated: 2026-08-05 16:20:57 · `fbafbf2e5d9b`*

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.48

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
- `gdb` — 15.1
- `git` — 2.43.0
- `libc6-dev-i386` — 2.39
- `libncurses6` — 6.4+20240113
- `libtinfo6` — 6.4+20240113
- `make` — 4.3
- `pciutils` — 3.10.0
- `unzip` — 6.0
- `vim` — 9.1.0016

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
  harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.7.2:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```
