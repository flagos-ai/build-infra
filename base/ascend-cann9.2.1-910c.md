## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910C
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
- CANN 910C Ops 9.2.1 (aarch64)
- CANN NNAL 9.2.1 (aarch64)

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --privileged \
  --shm-size=1g \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.2.1-910c:2.3.0 bash
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
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.2.1-910c:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
npu-smi info
```

## Changelog

### 2.3.0

*2026-11-13 00:45:50*

- First delivery: CANN 9.2.1 — the toolkit, the 910C (A3) ops package and
  NNAL — on aarch64 ubuntu:24.04.
- Only the ops package is chip-specific: this variant takes the `A3` token
  rather than `910b`; toolkit and NNAL are shared with the 910B line of
  the same CANN version.
- Carries python 3.12, matching the 910B row: the torch 2.13 stack this
  line exists for is cp312-only, and noble ships 3.12 so no PPA is needed.
- The 910C build nodes' docker 20.10.8 seccomp profile blocks `clone3`, so
  the apt `Post-Invoke` hooks are dropped; the build also takes the
  runner's proxy as build arguments, since these nodes have no direct
  egress.
- The SDK environment is captured into `/etc/profile.d/vendor.sh` at build
  time, so nothing has to be sourced inside the container.
- The three SDK packages come off the Nexus internal endpoint
  (`http://resource-inner.flagos.net:20800`): `resource.flagos.net` does
  not resolve on hw114/hw115, and the internal port is plain HTTP.
- That name lives only in the nodes' `/etc/hosts`, which build containers
  do not inherit, so `build-config.yml` `internal_hosts` makes
  `build_base.py` pass it in as `--add-host` with the address resolved on
  the runner.
