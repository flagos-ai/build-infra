---
title: "tsingmicro-tsm260604"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Tsingmicro TX8110
- **Host driver:** 260604163331.01
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: tx-container-toolkit >= 2.5.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1-30-gd767fb5`

### Python

3.10

### Major Python packages

- `flag_gems`
- `flagtree==0.5.0.post20260612+git705a4064`
- `torch==2.7.0+cpu`
- `torch_txda==0.1.0+20260615.37ba6bbd`
- `torchaudio==2.7.0+cpu`
- `torchvision==0.22.0+cpu`
- <span class="muted"><code class="plain">triton==3.3.0+gitfe2a28fa</code></span>
- `txops==0.1.0+20260508.60287151`

<p class="muted"><em>Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).</em></p>

## Environment

- `USE_TORCH_XLA=0`
- `TORCH_COMPILE_DISABLE=1`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  flagos-runtime-tsingmicro-tsm260604:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  flagos-runtime-tsingmicro-tsm260604:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
tsm_smi
```
