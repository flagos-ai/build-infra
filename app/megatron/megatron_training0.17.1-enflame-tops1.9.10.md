## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.9.10
- **Container toolkit** *(optional)*: tencent-container-toolkit >= 2.0.52

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.9.10:2.2.0`

### Python

3.12

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-enflame-tops1.9.10:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-enflame-tops1.9.10:2.2.0-0.2.3
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG megatron-train --model-type GPT
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG megatron-train --model-type GPT
```

## Changelog

### 2.2.0-0.2.3

*2026-09-29 01:10:16*

Rebuild on the enflame runtime rebuilt on FlagTree 0.7.0 (0.6.0/0.7.0rc2 → 0.7.0+enflame3.6, 2026-09-28). Same wheel and app pins as the image it replaces.

*2026-09-28 05:16:09*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-22 16:06:30*

Rebuilt on the FlagOS 2.2.0 stack and on release/0.2, whose head carries the app-image PRs now merged into it — the image this replaces installed a wheel built off their PR heads and an integration branch, so the platform fixes they carry were never in the artifact. The wheel is the one built from that line's release tag, and the install pin states it exactly (0.17.1+fl.0.2.3) rather than resolving ==0.17.1 to whichever local version the index held.

### 2.1.2-0.2.1_13_gc32a6e40e

*2026-08-31 14:43:52*

megatron-core wheel (0.17.1+fl) app image on this backend. Built on the MLF wheel-full-scope line (PR 107) with backend enablement carried by the listed MLF/vendor PRs. Single-step wheel install over the runtime.
