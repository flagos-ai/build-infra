## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 26.0.rc1
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
- `python3.11`
- `python3.11-dev`
- `software-properties-common`
- `unzip`
- `vim`

### SDK components

- CANN Toolkit 9.0.0 (aarch64)
- CANN 910B Ops 9.0.0 (aarch64)
- CANN NNAL 9.0.0 (aarch64)

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --privileged \
  --shm-size=1g \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.0.0:2.3.0 bash
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
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.0.0:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
npu-smi info
```

## Changelog

### 2.3.0

*2026-10-14 05:49:46*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-17 01:20:38*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-10 17:08:43*

- First delivery: CANN 9.0.0 — the toolkit, the 910B ops package and NNAL —
  on aarch64 ubuntu:24.04.
- python3.11 is force-installed from deadsnakes beside the distribution's
  3.12: the CANN installer writes python-version-specific artifacts the
  runtime imports, so the base interpreter has to equal the runtime venv's.
- The SDK environment is captured into `/etc/profile.d/vendor.sh` at build
  time, so nothing has to be sourced inside the container. Toolkit and NNAL
  `set_env.sh` are sourced under bash: they are bash scripts, and under dash
  they can take a path that calls `exit` and silently kill the step.
- ATB is in that capture because the toolkit's `set_env.sh` leaves
  `ATB_HOME_PATH` and the ATB library path out; without them `libatb.so`
  fails to load and the ATB operators (`_npu_reshape_and_cache`,
  `_npu_rotary_embedding`) crash at inference.
