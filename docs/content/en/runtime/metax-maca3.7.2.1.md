---
title: "metax-maca3.7.2.1"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.8.30
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: metax-docker >= 0.15.3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.1.1-30-gd767fb5`

### Python

3.12

### Major Python packages

- `flag_gems`
- `flagtree==3.1.0+metax3.7.2.0`
- `flash_attn==2.6.3+metax3.7.2.0torch2.8`
- `torch==2.8.0+metax3.7.2.0`
- `torchaudio==2.4.1+metax3.7.2.0`
- `torchvision==0.15.1+metax3.7.2.0`
- <span class="muted"><code class="plain">triton==3.0.0+metax3.7.2.0</code></span>

<p class="muted"><em>Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).</em></p>

## Launch

**With the container toolkit** *(optional)*:

```bash
metax-docker --gpus all flagos-runtime-metax-maca3.7.2.1:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  flagos-runtime-metax-maca3.7.2.1:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```
