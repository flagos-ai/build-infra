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

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-sunrise-tangrt1.2.0:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-sunrise-tangrt1.2.0:2.2.0-0.2.2
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
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.2.0-0.2.2

*2026-09-28 15:42:35*

Rebuild on a rebuilt sunrise runtime. The FlagTree sunrise wheel was faulty (missing sunriseTritonPlugin.so, so flag_gems could not import triton) and has been re-uploaded; runtime v2 :2.2.0 and v1 :2.2.0-build were rebuilt on it (digests 38eec/8b6fc). This app image was built on the broken runtime and is redone on the fixed one. Same plugin and app pins as the image it replaces.

*2026-09-28 07:23:30*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-20 10:33:38*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and FlagTree 0.6.0+sunrise3.6, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.0_g687217a.d20260819

*2026-08-20 02:26:28*

Initial 0.20.2 deliverable on Sunrise (PTPU). FlagTree PR 978 fixes the flagtree flash-attn decode hang (0.4->2.4 tok/s); rebuilt flagtree wheel carried in the runtime. F path verified.
