## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 5.0.1
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260816ubuntu0.24.04.2
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `libopenmpi3t64` — 4.1.6
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- Corex Runtime 5.0.1
- CUDA Header files 260604
- CMake (Iluvatar) 3.31.8

## Environment

- `COREX_ROOT=/usr/local/corex`
- `PATH=/usr/local/corex/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/corex/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex5.0.1:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  --device /dev/itrctl \
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex5.0.1:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```

*Last updated: 2026-11-12 21:36:52 · `1a2ee5aaa108`*

## Changelog

### 2.3.0

*2026-11-12 14:13:03*

- `libopenmpi3t64` provides the `libmpi.so.40` that corex 5.0.1's
  `libnvshmem_host.so` needs — torch reaches it through `torch_nvshmem`
  (`libtorch.so` and four more of its libraries carry the NEEDED entry),
  so `import torch` fails in the runtime without it.

*2026-11-12 09:22:38*

- The image now carries the CoreX driver userspace: libcuda.so.1,
  libixml.so and ixsmi are unpacked from the bundled driver installer into
  /usr/local/corex. The first build ran only the SDK installer, so
  `import torch` failed in the runtime with "libcuda.so.1: cannot open
  shared object file".

*2026-11-12 05:17:06*

- First corex5.0.1 base image: Iluvatar CoreX 5.0.1 SDK and driver 5.0.1,
  CUDA header 260604 and CMake 3.31.8 on Ubuntu 24.04. This line succeeds
  the retired corex4.4.0 and moves the stack to torch 2.13.
