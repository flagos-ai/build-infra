## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1
- **Host driver:** 0.24.0

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
- `git` — 2.43.0
- `pciutils` — 3.10.0
- `vim` — 9.1.0016

### SDK components

- Tang Toolkit 1.2.0
- PCCL 1.2.0
- taDNN 1.2.0
- taBLAS 1.2.0

## Environment

- `TANGRT_ROOT=/usr/local/tangrt`
- `LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`
- `LD_LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it \
  harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
pt_smi
```
