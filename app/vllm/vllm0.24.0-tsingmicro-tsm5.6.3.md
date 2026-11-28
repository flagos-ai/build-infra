## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Tsingmicro TX8110
- **Host driver:** 5.6.3.1112
- **Container toolkit** *(optional)*: tx-container-toolkit >= 2.5.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm5.6.3:2.3.0`

### Python

3.12

### Application package

`vllm==0.24.0+flagos`


`vllm-plugin-fl==0.3.0`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-tsingmicro-tsm5.6.3:2.3.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-tsingmicro-tsm5.6.3:2.3.0-0.3.0
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  $IMG vllm-serve --model <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.3.0-0.3.0

*2026-11-28 08:16:36*

- First delivery of this app on the TSM 5.6.3.1112 line, which is a
  different interpreter and torch from the 260610 line: python 3.12 and
  torch 2.13.0. Nothing is shared with the `tsingmicro-tsm260610` image.
