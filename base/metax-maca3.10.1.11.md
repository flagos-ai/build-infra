## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.100.1
- **Container toolkit** *(optional)*: metax-docker >= 0.15.3

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
- `git` — 2.43.0
- `libelf1`
- `libnuma1` — 2.0.18
- `libpython3-dev` — 3.12.3
- `make` — 4.3
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- MetaX Driver 3.100.1
- MACA SDK 3.10.1.11

## Environment

- `PATH=/opt/maca/mxgpu_llvm/bin:/opt/maca/bin:${PATH}`
- `MACA_PATH=/opt/maca`
- `LD_LIBRARY_PATH=/opt/maca/lib:/opt/maca/mxgpu_llvm/lib:/opt/maca/ompi/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.10.1.11:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.10.1.11:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```

*Last updated: 2026-11-18 19:46:07 · `a4c39b35c163`*

## Changelog

### 2.3.0

*2026-11-18 12:13:04*

- First delivery: MACA SDK 3.10.1.11 with driver 3.100.1 on ubuntu:24.04,
  for the MetaX C550 chip. This line replaces maca3.7.2.1.
- The driver is installed in userspace mode only, so the image builds
  headless; the kernel driver stays on the host, as with NVIDIA.
