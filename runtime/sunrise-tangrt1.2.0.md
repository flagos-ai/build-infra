## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1
- **Host driver:** 0.24.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.2`

### Python

3.10

### Major Python packages

- `flag_gems==5.3.2`
- `flagtree==0.6.0+sunrise3.6`
- `numpy==2.2.6`
- `torch-ptpu==0.2.3+torch2.11`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- `triton==3.6.0.1+git0a5cfb35` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-sunrise-tangrt1.2.0:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
pt_smi
```
