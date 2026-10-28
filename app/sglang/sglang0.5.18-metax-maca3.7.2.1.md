## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.8.30
- **Container toolkit** *(optional)*: metax-docker >= 0.15.3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.7.2.1:2.1.2`

### Python

3.12

### Application package

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+ga73b27b60`

## Environment

- `TORCHINDUCTOR_COMPILE_THREADS=1`
- `SGLANG_IS_FLASHINFER_AVAILABLE=false`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-metax-maca3.7.2.1:2.1.2-0.1.dev1_ga73b27b60`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-metax-maca3.7.2.1:2.1.2-0.1.dev1_ga73b27b60
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
metax-docker run --rm -it $IMG bash
```

Start the app with its default settings:

```bash
metax-docker run --rm -it $IMG
```

Pass arguments to the launcher:

```bash
metax-docker run --rm -it $IMG sglang-serve --model-path <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.1.2-0.1.dev1_ga73b27b60

*2026-09-07 16:08:21*

sglang 0.5.18 on metax maca3.7.2.1. sglang-plugin-FL PR 86: vendor patch for the three JIT/flashinfer guards.
