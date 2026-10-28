## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.2.15

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.4.3:2.2.0`

### Python

3.10

### Application package

`megatron-core[rl]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-cambricon-neuware4.4.3:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-cambricon-neuware4.4.3:2.2.0-0.2.3
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.

## Changelog

### 2.2.0-0.2.3

*2026-09-28 05:23:56*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-23 13:40:23*

First megatron_rl image on this backend. The RL line resumes for image publication after MLF PR 114 declared the [rl] extra and PR 116 replaced the hard flash-attn >= 2.7.3 assert with a platform / DotProductAttention gate. Built on the FlagOS 2.2.0 stack with the release-line wheel, pinned exactly (0.17.1+fl.0.2.3) rather than resolving ==0.17.1 to whichever local version the index held. This backend ships no flash-attn, so the ungated dynamic-batching path needs --attention-backend unfused (DotProductAttention is exempt from the gate). The RL scenario has not been measured on this image.
