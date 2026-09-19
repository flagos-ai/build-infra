## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** *(optional)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.2.0`

### Python

3.10

### Major Python packages

- `flag_gems==5.4.0-rc2.post3`
- `flagtree==0.7.0rc2+mthreads3.6`
- `mkl==2024.0.0`
- `numpy==1.26.4`
- `torch==2.9.1+musa5.2.0`
- `torch_musa==2.9.1`
- `torchaudio==2.9.1+musa5.2.0`
- `torchvision==0.24.1.post1+musa5.2.0`
- `triton==3.6.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:2.2.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:2.2.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```
