## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2`

### Python

3.10

### Application package

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g440208beb`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-hygon-dtk26.04:2.1.2-0.1.dev1_g440208beb`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-hygon-dtk26.04:2.1.2-0.1.dev1_g440208beb
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  $IMG sglang-serve --model-path <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.1.2-0.1.dev1_g440208beb

*2026-09-08 00:00:00*

sglang 0.5.18 on hygon DTK 26.04. sglang-plugin-FL PR 98: make sglang serve on the CUDA-alias runtime.
