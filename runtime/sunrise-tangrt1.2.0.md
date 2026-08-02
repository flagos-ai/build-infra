## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1
- **Host driver:** 0.24.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1`

### Python

3.10

### Major Python packages

- `flag_gems==5.3.2`
- `numpy==2.2.6`
- `torch-ptpu==0.2.3+torch2.11`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- `triton==3.4.0.6+gite4f6d6e4`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-sunrise-tangrt1.2.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
pt_smi
```
