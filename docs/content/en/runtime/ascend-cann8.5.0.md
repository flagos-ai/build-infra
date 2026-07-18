---
title: "ascend-cann8.5.0"
---

## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 25.5.0
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1-30-gd767fb5`

### Python

3.11

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0+ascend3.2`
- `torch-npu==2.9.0`
- `torch==2.9.0+cpu`
- <span class="muted"><code class="plain">triton-ascend==3.2.0</code></span>

<p class="muted"><em>Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).</em></p>

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  flagos-runtime-ascend-cann8.5.0:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  flagos-runtime-ascend-cann8.5.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh && npu-smi info
```
