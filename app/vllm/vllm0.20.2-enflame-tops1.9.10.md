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

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-enflame-tops1.9.10:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-enflame-tops1.9.10:2.2.0-0.2.2
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
  $IMG vllm-serve --model <path> --port 9000
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
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.2.0-0.2.2

*2026-09-29 01:00:48*

Rebuild on the enflame runtime rebuilt on FlagTree 0.7.0 (0.6.0/0.7.0rc2 → 0.7.0+enflame3.6, 2026-09-28). Same plugin and app pins as the image it replaces.

*2026-09-28 06:55:35*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-20 06:19:43*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and FlagTree 0.6.0+enflame3.6, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.2rc2.post1_gdcc8966.d20260916

*2026-09-16 10:56:49*

Rebuild on the vllm-plugin-FL 0.2.2-rc2 branch head dcc8966 — PR 357, the first time the GCU300 work is on the release line. GCU attention moves off the plugin's standalone AttentionGCUBackend onto vLLM's native FlashAttentionBackend, reached through Enflame's flash_attn package (new impl/flash_attn_backend.py and impl/slot_mapping.py), and enflame.yaml's flagos_blacklist grows the int64-IR ops the GCU300 PassManager rejects plus the sampling sort/top-k path and argmax, which go back to torch_gcu. The images were previously built from the pre-merge enflame branch (c2e496d), whose commits never reached this line. The wheel version base follows the branch's own version (0.2.2rc2.post1), as the metax 0.20.2 images do.

### 2.1.2-0.2.1_gc2e496d.d20260905

*2026-09-05 13:04:34*

Initial 0.20.2 deliverable on GCU300 (tops1.9.10), cross-stack with tops1.10.6: vllm-plugin-FL rotary flash_attn import guard (c2e496d) + repacked vllm wheel pinning xgrammar==0.2.3+flagos. F/T both serve correctly (Paris anchor).
