## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** *(optional)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.1.1`

### Python

3.10

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0+mthreads3.6`
- `mkl==2024.0.0`
- `torch==2.9.0+musa5.2.0`
- `torch_musa==2.9.1`
- `triton==3.6.0` *(fallback)*

*Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).*

## Environment

- `MTHREADS_VISIBLE_DEVICES=all`
- `LD_LIBRARY_PATH=${VIRTUAL_ENV}/lib:${LD_LIBRARY_PATH}`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```
