## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.9.6
- **Container toolkit** *(optional)*: metax-docker >= 0.15.3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.8.1.3:2.2.0`

### Python

3.12

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-metax-maca3.8.1.3:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-metax-maca3.8.1.3:2.2.0-0.2.3
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

*2026-09-28 05:13:27*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-22 16:06:40*

First app image for this backend. The row's E2E runs are green on both compiler paths but no image was ever built for it, so the entry point to the work was the playbook rather than an artifact. Built on the FlagOS 2.2.0 stack and on the megatron-core wheel from release/0.2's release tag, pinned to its exact version (0.17.1+fl.0.2.3).
