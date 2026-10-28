## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.2.0`

### Python

3.12

### Application package

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-iluvatar-corex4.4.0:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-iluvatar-corex4.4.0:2.2.0-0.2.2
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

### 2.2.0-0.2.2

*2026-09-28 11:59:13*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-28 10:16:28*

Rebuild on the 4.4.0 runtime with FlagTree downgraded to 0.6.1 (0.7.0 hard-loads libflagcx.so; the CoreX 4.4.0 SDK ships no libixccl, so the runtime failed to import flag_gems). Same stack, plugin and app pins as the 0.7.0-era image it replaces.

*2026-09-23 11:00:43*

Rebuild on a corrected base image. The CoreX cmake installer was being handed a flag it silently ignores, so every image in this chain shipped a cmake that cannot run (#1011). Nothing else moves: same stack, same base and runtime recipe, same plugin pin.

*2026-09-20 10:55:02*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and the 0.7.0-era FlagTree, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.1_g16e8655.d20260907

*2026-09-07 11:06:11*

Determinism fix on corex4.4.0: blacklist the flag_gems GEMM family (linear/mm/addmm/bmm) so GEMMs fall back to native corex ixblas. Flagtree-compiled flag_gems GEMM kernels are launch-to-launch nondeterministic in the live engine (~1-2 bf16 ulp), flipping temp=0 decode at near-tie bands; native GEMMs are deterministic and faster. F/T both 30/30 temp=0-deterministic. Earlier publishes (gec9fded: pytorch sampler fallback + torch<2.8 symm_mem guard wheel; g71b9482: silu_and_mul blacklist) were not temp=0-deterministic and are superseded.
