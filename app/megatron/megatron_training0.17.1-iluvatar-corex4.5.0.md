## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.5.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.5.0:2.2.0`

### Python

3.12

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.5.0:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.5.0:2.2.0-0.2.3
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  $IMG megatron-train --model-type GPT
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  --device /dev/itrctl \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  --device /dev/itrctl \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  --device /dev/itrctl \
  $IMG megatron-train --model-type GPT
```

## Changelog

### 2.2.0-0.2.3

*2026-09-28 05:15:15*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-23 10:54:36*

Rebuild on a corrected base image. The CoreX cmake installer was being handed a flag it silently ignores, so every image in this chain shipped a cmake that cannot run (#1011). Nothing else moves: same stack, same base and runtime recipe, same wheel pin.

*2026-09-22 16:04:23*

Rebuilt on the FlagOS 2.2.0 stack and on release/0.2, whose head carries the app-image PRs now merged into it — the image this replaces installed a wheel built off their PR heads and an integration branch, so the platform fixes they carry were never in the artifact. The wheel is the one built from that line's release tag, and the install pin states it exactly (0.17.1+fl.0.2.3) rather than resolving ==0.17.1 to whichever local version the index held.

### 2.1.2-0.2.1_15.g56acf36ba

*2026-08-31 07:28:42*

megatron-core wheel (0.17.1+fl) app image on this backend. Built on the MLF wheel-full-scope line (PR 107) with backend enablement carried by the listed MLF/vendor PRs. Single-step wheel install over the runtime.
