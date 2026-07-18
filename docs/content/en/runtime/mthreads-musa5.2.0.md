---
title: "mthreads-musa5.2.0"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.1.1-30-gd767fb5`

### Python

3.10

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0+mthreads3.6`
- `mkl==2024.0.0`
- `torch==2.9.0+musa5.2.0`
- `torch_musa==2.9.1`
- <span class="muted"><code class="plain">triton==3.6.0</code></span>

<p class="muted"><em>Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).</em></p>

## Environment

- `MTHREADS_VISIBLE_DEVICES=all`
- `LD_LIBRARY_PATH=${VIRTUAL_ENV}/lib:${LD_LIBRARY_PATH}`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  flagos-runtime-mthreads-musa5.2.0:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  flagos-runtime-mthreads-musa5.2.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```
