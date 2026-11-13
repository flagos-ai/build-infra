## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 26.1.1
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

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
- `libpython3-dev`
- `make`
- `net-tools`
- `pciutils`
- `python3-pip`
- `python3.12`
- `python3.12-dev`
- `unzip`
- `vim`

### SDK components

- CANN Toolkit 9.2.1 (aarch64)
- CANN 910B Ops 9.2.1 (aarch64)
- CANN NNAL 9.2.1 (aarch64)

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --privileged \
  --shm-size=1g \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.2.1:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --shm-size=1g \
  --device /dev/davinci0 \
  --device /dev/davinci1 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.2.1:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
npu-smi info
```

## Changelog

### 2.3.0

*2026-11-04 14:05:09*

- Re-push with the OCI provenance labels the first build could not write:
  `org.opencontainers.image.revision`, `.created` and `last-updated`.
- Image content is unchanged. Without the revision label,
  `scripts/base_image_status.py` reports this backend UNKNOWN and cannot
  answer whether the pushed image is behind HEAD.

*2026-11-03 10:55:38*

- First delivery: CANN 9.2.1 — toolkit, the 910B ops package and NNAL — on
  aarch64 ubuntu:24.04.
- Carries python 3.12 rather than 3.11. The torch 2.13.0 / torch_npu 2.13.0
  stack this line exists for is cp312-only.
- The SDK environment is captured into `/etc/profile.d/vendor.sh` at build
  time, so nothing has to be sourced inside the container.
