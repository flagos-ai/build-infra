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

`megatron-core[rl]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-enflame-tops1.9.10:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-enflame-tops1.9.10:2.2.0-0.2.3
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

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.


### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.

## Changelog

### 2.2.0-0.2.3

*2026-09-29 02:27:05*

Rebuild on the enflame runtime rebuilt on FlagTree 0.7.0 (0.6.0/0.7.0rc2 → 0.7.0+enflame3.6, 2026-09-28). Same wheel and app pins as the image it replaces.

*2026-09-28 05:29:37*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-23 13:48:50*

First megatron_rl image on this backend. The RL line resumes for image publication after MLF PR 114 declared the [rl] extra and PR 116 replaced the hard flash-attn >= 2.7.3 assert with a platform / DotProductAttention gate. Built on the FlagOS 2.2.0 stack with the release-line wheel, pinned exactly (0.17.1+fl.0.2.3) rather than resolving ==0.17.1 to whichever local version the index held.
