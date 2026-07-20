## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.29.0.0
- **Container toolkit** *(optional)*: xpu_container >= 1.0.13

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1`

### Python

3.10

### Major Python packages

- `apex==0.1`
- `benchflow==1.0.0`
- `colorama==0.4.6`
- `flag_gems`
- `flagtree==0.5.1+xpu3.0`
- `flash_attn==2.4.2+7e2dd4d`
- `hydrax==0.1.0`
- `hyperparameter==0.5.6`
- `psutil==6.1.0`
- `regex==2026.4.4`
- `torch==2.9.0+cu129`
- `torch_plugin==0.1.0`
- `torch_xray==2.0.4`
- `torchaudio==2.9.0+cu129`
- `torchvision==0.24.0+cu129`
- `triton==3.0.0+a48aedef` *(fallback)*
- `xformers==0.0.29+1e7a8ec.d20260114`
- `xmlir==1.0.0.1`

*Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).*

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-kunlunxin-xre5.29.0:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-kunlunxin-xre5.29.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
xpu-smi
```
