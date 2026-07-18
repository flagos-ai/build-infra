## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.2.15

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.1.1-30-gd767fb5`

### Python

3.10

### Major Python packages

- `cambricon_dali==0.13.0`
- `flag_gems`
- `torch-mlu-ops==1.8.0+torch2.7.1`
- `torch-mlu==1.29.2+torch2.7.1`
- `torch==2.7.1+cpu`
- `triton==3.2.0+mlu1.7.2`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  flagos-runtime-cambricon-neuware4.4.3:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```
