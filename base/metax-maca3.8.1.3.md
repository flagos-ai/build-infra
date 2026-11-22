## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.9.6
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
- `libjpeg-turbo8` — 2.1.5
- `libnuma1` — 2.0.18
- `libpng16-16t64` — 1.6.43
- `libpython3-dev` — 3.12.3
- `make` — 4.3
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- MetaX Driver 3.8.1.6
- MACA SDK 3.8.1.3

## Environment

- `PATH=/opt/maca/mxgpu_llvm/bin:/opt/maca/bin:${PATH}`
- `MACA_PATH=/opt/maca`
- `LD_LIBRARY_PATH=/opt/maca/lib:/opt/maca/mxgpu_llvm/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.8.1.3:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.8.1.3:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```

*Last updated: 2026-11-22 19:37:45 · `8222d6f89174`*

## Changelog

### 2.3.0

*2026-11-22 11:54:00*

- Installs libjpeg-turbo8 (libjpeg.so.8) and libpng16-16t64
  (libpng16.so.16). MetaX's torchvision wheel is not auditwheel-bundled,
  so image.so links those system sonames; without them the import raised
  "Failed to load image Python extension" and torchvision.io PNG/JPEG
  encode/decode was unavailable.

*2026-10-14 05:49:44*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:44:47*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-14 15:04:10*

- First delivery: MACA 3.8.1.3 with driver 3.8.1.6 on ubuntu:24.04,
  alongside the 3.7.2.1 line.
- The driver is installed in userspace mode only, so the image builds
  headless; the kernel driver stays on the host, as with NVIDIA.
- `MACA_PATH`, `PATH` and `LD_LIBRARY_PATH` are set in the image, so the
  toolkit is usable without an activation step.
