## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.3.0-server
- **Container toolkit** *(optional)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

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
- `git`
- `libelf1`
- `libgfortran5`
- `libnuma-dev`
- `libopenmpi-dev`
- `libpython3-dev`
- `openmpi-bin`
- `unzip`
- `vim`

### SDK components

- MUSA Toolkits 5.3.0
- MCCL 2.5.0
- muDNN 3.5.0

## Environment

- `MUSA_HOME=/usr/local/musa`
- `PATH=/usr/local/musa/bin:${PATH}`
- `LD_LIBRARY_PATH=/usr/local/musa/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.3.0:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.3.0:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```

## Changelog

### 2.3.0

*2026-11-14 08:07:35*

- First delivery: MUSA 5.3.0 with MCCL 2.5.0 and muDNN 3.5.0 on
  ubuntu:24.04, alongside the RC4.3.6 and 5.2.0 lines.
- The vendor's driver is installed from its own `.deb`, so the device's
  userspace comes from the container, and the build toolchain, OpenMPI and
  the Python development headers are installed beside the SDK.
- This is the first mthreads line on 24.04 and the first whose Python
  stack is 3.12; the runtime brings its own interpreter, so the system one
  is not the row's.
