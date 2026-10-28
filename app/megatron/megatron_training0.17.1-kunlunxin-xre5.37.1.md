## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.37.1
- **Container toolkit** *(optional)*: xpu_container >= 1.0.13

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-kunlunxin-xre5.37.1:2.2.0`

### Python

3.10

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-kunlunxin-xre5.37.1:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-kunlunxin-xre5.37.1:2.2.0-0.2.3
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  $IMG megatron-train --model-type GPT
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  $IMG megatron-train --model-type GPT
```

## Changelog

### 2.2.0-0.2.3

*2026-09-28 05:14:01*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-23 07:21:30*

First publication of the training app image on this backend. The megatron-core wheel is built from the Megatron-LM-FL release line's head, which now carries the platform PRs merged into it (MLF 180 txda graph-capture query, MLF 181 Sunrise PT-PU platform), and the single-step install pin states the wheel exactly (0.17.1+fl.0.2.3) rather than resolving ==0.17.1 to whichever local version the index held. No vendor-side PR is pending.
