## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:TBD`

### Python

3.10

### Application package

`vllm==0.32.0+flagos`

## Launch

**Not published yet — this image is not on the registry yet. `TBD` is the tag the build pipeline assigns when it builds the image for this backend.**

`harbor.baai.ac.cn/flagos-app/vllm0.32.0-hygon-dtk26.04:TBD`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.32.0-hygon-dtk26.04:TBD
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
