## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1
- **Host driver:** 0.24.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-sunrise-tangrt1.2.0:2.2.0`

### Python

3.10

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-sunrise-tangrt1.2.0:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-sunrise-tangrt1.2.0:2.2.0-0.2.3
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  -e TANG_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  -e TANG_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  -e TANG_VISIBLE_DEVICES=all \
  $IMG megatron-train --model-type GPT
```

## Changelog

### 2.2.0-0.2.3

*2026-09-28 15:57:10*

Rebuild on a rebuilt sunrise runtime. The FlagTree sunrise wheel was faulty (missing sunriseTritonPlugin.so, so flag_gems could not import triton) and has been re-uploaded; runtime v2 :2.2.0 and v1 :2.2.0-build were rebuilt on it (digests 38eec/8b6fc). This app image was built on the broken runtime and is redone on the fixed one. Same plugin and app pins as the image it replaces.

*2026-09-28 05:16:17*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-23 07:23:20*

First publication of the training app image on this backend. The megatron-core wheel is built from the Megatron-LM-FL release line's head, which now carries the platform PRs merged into it (MLF 180 txda graph-capture query, MLF 181 Sunrise PT-PU platform), and the single-step install pin states the wheel exactly (0.17.1+fl.0.2.3) rather than resolving ==0.17.1 to whichever local version the index held. No vendor-side PR is pending.
