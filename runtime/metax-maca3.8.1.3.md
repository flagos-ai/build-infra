## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.9.6
- **Container toolkit** *(optional)*: metax-docker >= 0.15.3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.8.1.3:2.1.2`

### Python

3.12

### Major Python packages

- `apex==0.1+metax3.8.1.0`
- `flag_gems==5.3.5`
- `flagtree==0.6.1+metax3.6`
- `flash_attn==2.6.3+metax3.8.1.0torch2.10`
- `flash_linear_attention==0.5.0+metax3.8.1.0torch2.10`
- `flash_mla==1.0.1+metax3.8.1.0torch2.10`
- `flashinfer==0.2.6+metax3.8.1.0torch2.10`
- `numpy==2.3.5`
- `torch==2.10.0+metax3.8.1.0`
- `torchaudio==2.4.1+metax3.8.1.0`
- `torchcodec==0.6.0+metax3.8.1.0`
- `torchvision==0.25.0+metax3.8.1.0`
- `triton==3.6.0+metax3.8.1.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.8.1.3:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.8.1.3:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```
