## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 26.0.rc1
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann9.0.0:2.1.2`

### Python

3.11

### Application package

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g2e568482e`

## Environment

- `USE_FLAGGEMS=0`
- `TORCHINDUCTOR_COMPILE_THREADS=1`
- `SGLANG_IS_FLASHINFER_AVAILABLE=false`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-ascend-cann9.0.0:2.1.2-0.1.dev1_g2e568482e`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-ascend-cann9.0.0:2.1.2-0.1.dev1_g2e568482e
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
  $IMG sglang-serve --model-path <path> --port 9000
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
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.1.2-0.1.dev1_g2e568482e

*2026-09-03 14:08:15*

sglang 0.5.18 on Ascend cann9.0.0 (PR 84 zero-kernel stand-ins).
