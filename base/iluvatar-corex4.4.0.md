## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `unzip` — 6.0

### SDK components

- Corex Runtime 4.4.0
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
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```
