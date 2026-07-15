---
title: "ascend-cann8.5.0"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1`

## Prerequisites

- **Operating system:** `ubuntu:22.04`
- **Architecture:** aarch64
- **Chip models:** Ascend 910B

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `libelf1` — 0.186
- `libpython3-dev` — 3.10.6
- `make` — 4.3
- `net-tools` — 1.60+git20181103.0eebece
- `pciutils` — 3.7.0
- `python3-pip` — 22.0.2+dfsg
- `python3.11` — 3.11.0~rc1
- `python3.11-dev` — 3.11.0~rc1
- `unzip` — 6.0

## SDK components

- CANN Toolkit 8.5.0 (aarch64)
- CANN 910B Ops 8.5.0 (aarch64)

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it --device /dev/davinci0 --device /dev/davinci_manager --device /dev/devmm_svm --device /dev/hisi_hdc -v /usr/local/Ascend/driver:/usr/local/Ascend/driver -v /usr/local/dcmi:/usr/local/dcmi -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
npu-smi info
```
