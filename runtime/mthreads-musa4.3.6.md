## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** *(optional)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa4.3.6:2.1.2`

### Python

3.10

### Major Python packages

- `flag_gems==5.3.4`
- `flagtree==0.6.0+mthreads3.6`
- `mkl==2024.0.0`
- `numpy==1.26.4`
- `torch==2.9.0+musa.4.3.6`
- `torch_musa==2.9.0`
- `triton==3.6.0+git89458660` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa4.3.6:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa4.3.6:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```
