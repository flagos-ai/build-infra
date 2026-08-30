## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.5.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Base image

`ubuntu:24.04`

### SDK components

- Corex Runtime 4.5.0
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
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.5.0:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.5.0:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```

*Last updated: 2026-08-30 07:33:59 · `175149b4f729`*
