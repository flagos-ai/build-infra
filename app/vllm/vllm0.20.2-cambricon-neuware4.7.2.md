## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.48

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.2:2.2.0`

### Python

3.12

### Application package

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-cambricon-neuware4.7.2:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-cambricon-neuware4.7.2:2.2.0-0.2.2
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.2.0-0.2.2

*2026-09-28 06:39:21*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-20 11:14:33*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and the vendor's own Triton, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.1_gb954912.d20260904

*2026-09-04 23:41:57*

Rebuild on flag_gems 5.3.5 (FlagGems mask-logic fix) after re-verify on neuware4.7.2, correcting a numpy mismatch (2.2.6 pulled into the earlier app image vs the runtime's 1.26.4 pin). Repacked vllm wheel pins xgrammar==0.2.3+flagos; single-step install is matrix-inert; semantic serve verified. Supersedes the initial 0.20.2 deliverable (same tag prefix, gb954912.d20260826, PR 411 cambricon enablement with the flag_gems index blacklist).
