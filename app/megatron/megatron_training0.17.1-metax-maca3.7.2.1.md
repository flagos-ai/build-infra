## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.8.30
- **Container toolkit** *(optional)*: metax-docker >= 0.15.3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.7.2.1:2.2.0`

### Python

3.12

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-metax-maca3.7.2.1:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-metax-maca3.7.2.1:2.2.0-0.2.3
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
metax-docker run --rm -it $IMG bash
```

Start the app with its default settings:

```bash
metax-docker run --rm -it $IMG
```

Pass arguments to the launcher:

```bash
metax-docker run --rm -it $IMG megatron-train --model-type GPT
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  $IMG megatron-train --model-type GPT
```

## Changelog

### 2.2.0-0.2.3

*2026-09-28 05:15:16*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-23 07:24:31*

First publication of the training app image on this backend. The megatron-core wheel is built from the Megatron-LM-FL release line's head, which now carries the platform PRs merged into it (MLF 180 txda graph-capture query, MLF 181 Sunrise PT-PU platform), and the single-step install pin states the wheel exactly (0.17.1+fl.0.2.3) rather than resolving ==0.17.1 to whichever local version the index held. No vendor-side PR is pending.
