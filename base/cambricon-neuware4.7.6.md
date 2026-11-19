## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.52

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260816ubuntu0.24.04.2
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

- cnmon 6.5.52
- cntoolkit 4.7.6
- cncl 1.30.10
- cnclep 1.5.0
- cnnl 2.2.18
- cnnlextra 2.5.0
- mluops 1.13.0
- cncv 2.12.1

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
  harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.7.6:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```

*Last updated: 2026-11-19 14:02:11 · `5943ca96f622`*

## Changelog

### 2.3.0

*2026-11-19 06:11:38*

- First delivery: Cambricon Neuware 4.7.6 — cntoolkit 4.7.6, cnnl 2.2.18,
  cnnlextra 2.5.0, mluops 1.13.0, cncl 1.30.10, cncv 2.12.1, cnclep 1.5.0
  and cnmon 6.5.52 — on ubuntu:24.04. This line is the newest of the
  vendor's SDK lines; neuware4.7.2 stays in service beside it.
- `NEUWARE_HOME`, `PATH` and `LD_LIBRARY_PATH` are set in the image, so the
  toolkit is usable without an activation step.
