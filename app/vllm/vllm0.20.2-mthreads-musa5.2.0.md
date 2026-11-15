## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** *(optional)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:2.2.0`

### Python

3.10

### Application package

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-mthreads-musa5.2.0:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-mthreads-musa5.2.0:2.2.0-0.2.2
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  $IMG vllm-serve --model <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.2.0-0.2.2

*2026-09-29 09:32:46*

Rebuild on the mthreads runtime rebuilt with the updated flagtree wheel (same 0.7.0+mthreads3.6 version, new contents, 2026-09-29). Same plugin and app pins as the image it replaces.

*2026-09-28 06:37:03*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-20 10:57:37*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and the 0.7.0-era FlagTree, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index. What matters for MUSA: the previous published image was a bare 2.1.2 tag carrying no plugin, so this is the first 0.20.2 deliverable here that installs vllm-plugin-FL — it ships the MUSA enablement the plugin holds (v1 attention backend registry, the use_sparse argument on attention_backend, and the torch.accelerator / torch.cuda shims for MUSA). The earlier 2.2.0 attempt (temp-form post1) never reached the registry — it built but failed app-image verification.

### 2.1.2

*2026-08-24 07:02:14*

Initial 0.20.2 deliverable on MooreThreads MUSA (no vllm-plugin-fl in this line — bare tag, app installs the repacked wheel only). F/T dual-path app-image pass recorded 2026-08-24.
