## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.48

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.7.2:2.1.2`

### Python

3.12

### Major Python packages

- `flag_gems==5.3.2`
- `numpy==2.2.6`
- `torch-mlu-ops==1.12.1+torch2.11.0`
- `torch-mlu==1.33.1+torch2.11.0`
- `torch==2.11.0+cpu`
- `triton==3.4.0+mlu2.1.1`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.2:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```
