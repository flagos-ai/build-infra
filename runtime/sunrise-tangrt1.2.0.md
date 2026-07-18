## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1
- **Host driver:** 0.24.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1-30-gd767fb5`

### Python

3.10

### Major Python packages

- `flag_gems`
- `torch-ptpu==0.2.3+torch2.11`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- `triton==3.4.0.6+gite4f6d6e4`

## Launch

Start an interactive shell in the container:

```bash
docker run --rm -it flagos-runtime-sunrise-tangrt1.2.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
pt_smi
```
