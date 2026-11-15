## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** *(optional)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa4.3.6:2.2.0`

### Python

3.10

### Application package

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g607b9672c`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-mthreads-musa4.3.6:2.2.0-0.1.dev1_g607b9672c`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-mthreads-musa4.3.6:2.2.0-0.1.dev1_g607b9672c
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  $IMG sglang-serve --model-path <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.2.0-0.1.dev1_g607b9672c

*2026-09-29 08:45:02*

Rebuild on the FlagOS 2.2.0 stack and the mthreads runtime rebuilt with the updated flagtree wheel (same 0.7.0+mthreads3.6 version, new contents, 2026-09-29). Same sglang and plugin pins as the 2.1.2 image it replaces (PR 92 head, still open).

### 2.1.2-0.1.dev1_g607b9672c

*2026-09-06 03:51:47*

sglang 0.5.18 on mthreads musa4.3.6. sglang-plugin-FL PR 92: make sglang 0.5.18 serve on the torch_musa runtime.
