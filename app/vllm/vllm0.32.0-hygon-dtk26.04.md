## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.3.0`

### Python

3.10

### Application package

`vllm==0.32.0+flagos`


`vllm-plugin-fl==0.5.0.dev0+g4856534.d20261125`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.32.0-hygon-dtk26.04:2.3.0-0.5.0.dev0_g4856534.d20261125`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.32.0-hygon-dtk26.04:2.3.0-0.5.0.dev0_g4856534.d20261125
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
  $IMG vllm-serve --model <path> --port 9000
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
  $IMG vllm-serve --model <path> --port 9000
```
