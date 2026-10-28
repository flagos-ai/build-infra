## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910C
- **Host driver:** 26.0.rc1
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann9.0.0-910c:2.2.0`

### Python

3.11

### Application package

`megatron-core[training]==0.18.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.18.2-ascend-cann9.0.0-910c:2.2.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.18.2-ascend-cann9.0.0-910c:2.2.0-0.3.0
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --privileged \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  $IMG megatron-train --model-type GPT
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci1 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci1 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci1 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  $IMG megatron-train --model-type GPT
```

## Changelog

### 2.2.0-0.3.0

*2026-09-29 08:57:04*

First megatron-core 0.18.2 app image on ascend-cann9.0.0-910c. Built on the FlagOS 2.2.0 stack from the MLF v0.3.0 wheel (0.18.2+0.3.0, 128dbd4f3). deps_app key + status-matrix rows landed via build-infra #1296 after the on-node F/T dual-compiler E2E passed (pretrain_gpt 5-iter exit 0, loss bit-identical).
