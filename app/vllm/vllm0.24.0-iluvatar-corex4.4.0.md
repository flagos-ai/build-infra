## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.3.0`

### Python

3.12

### Application package

`vllm==0.24.0+flagos`


`vllm-plugin-fl==0.3.0`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-iluvatar-corex4.4.0:2.3.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-iluvatar-corex4.4.0:2.3.0-0.3.0
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
  $IMG vllm-serve --model <path> --port 9000
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
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.3.0-0.3.0

*2026-10-26 12:20:37*

- The runtime introduces two container-start flags,
  `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>`,
  which override the compiler and FlagGems versions baked into the image. A
  request that cannot be honoured stops the container instead of letting it
  run on another version.
- flagcx 0.14.0 is now a runtime dependency, pinned as
  flagcx==0.14.0+corex4.4.0.

### 2.2.0-0.3.0

*2026-09-28 14:02:12*

The 0.24.0 line moves to the vllm-plugin-FL formal release v0.3.0 (tag = commit f105277). The plugin now ships as the release version (vllm-plugin-fl==0.3.0, one py3-none-any wheel, sha adf5a9e3...451f62, on every vendor index) instead of the v0.3.0-rc2.post2 delivery tag. Same stack and app pins as the rc2.post2 image it replaces; the only delta is the formal release of the same code.

### 2.2.0-0.3.0rc2.post3

*2026-09-28 21:17:04*

The symmetric-memory stub on the release line catches ImportError now, not just ModuleNotFoundError (vllm-plugin-FL v0.3.0-rc2.post3): the iluvatar corex torch 2.7.1 ships torch.distributed._symmetric_memory whose import of torch._C._distributed_c10d._SymmetricMemory raises ImportError (a torch 2.8 symbol), so the old stub never fired and the plugin could not load. post3 is the first wheel with the fix and is on the iluvatar index. Same stack (0.6.1 flagtree + USE_FLAGTUNE_COST_MODEL=0) and app pins as the post2 image it replaces; the T path stays undeliverable on the vendor corex triton 3.1 defect (iluvatar backend doc §14.4).

### 2.2.0-0.3.0rc2.post2

*2026-09-28 18:16:28*

Rebuild on the 4.4.0 runtime with FlagTree downgraded to 0.6.1 (0.7.0 hard-loads libflagcx.so; the CoreX 4.4.0 SDK ships no libixccl, so the runtime failed to import flag_gems). Same stack, plugin and app pins as the 0.7.0-era image it replaces. The T path stays undeliverable on the vendor corex triton 3.1 defect (iluvatar backend doc §14.4); this rebuild reruns the F path only.

*2026-09-20 17:43:35*

The symmetric-memory stub (PR 491) is on the release line now, so this image leaves c9e2573, a commit of the main line. The F path stays the deliverable one; the T path remains undeliverable on the vendor corex triton 3.1 defect recorded in the iluvatar backend doc. Rebuilt on the FlagOS 2.2.0 stack, whose base and runtime carry FlagGems 5.4.0-rc2.post3, and on the vllm-plugin-FL release tag v0.3.0-rc2.post2 (0891073, head of 0.3.0-rc2): the plugin comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.1_gc9e2573.d20260913

*2026-09-13 14:43:58*

Rebuild on the unified vllm-plugin-FL head that carries the symm_mem stub, superseding the one-off wheel pinned to VPF #434. F path deliverable; T path not deliverable (vendor corex triton 3.1 defect, see the iluvatar backend doc).

### 2.1.2-0.2.1_g84a4ca2.d20260902

*2026-09-02 12:14:27*

vllm 0.24.0 on iluvatar corex4.4.0 (PR 434 symm_mem stub for torch<2.8). F path deliverable; T path not deliverable (vendor corex triton 3.1 defect, see iluvatar doc).
