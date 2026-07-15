---
title: "ascend-cann9.0.0"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.0.0:2.1.1`

## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910B

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `curl`
- `g++`
- `gcc`
- `libelf1`
- `libpython3-dev`
- `make`
- `net-tools`
- `pciutils`
- `python3-pip`
- `python3.11`
- `python3.11-dev`
- `unzip`

## SDK components

- CANN Toolkit 9.0.0 (aarch64)
- CANN 910B Ops 9.0.0 (aarch64)
- CANN NNAL 9.0.0 (aarch64)

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --device /dev/davinci0 --device /dev/davinci_manager --device /dev/devmm_svm --device /dev/hisi_hdc -v /usr/local/Ascend/driver:/usr/local/Ascend/driver -v /usr/local/dcmi:/usr/local/dcmi -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.0.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
npu-smi info
```
