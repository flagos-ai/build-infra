## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Tsingmicro TX8110
- **Host driver:** 260610164501.01
- **Container toolkit** *(optional)*: tx-container-toolkit >= 2.5.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm260610:2.2.0`

### Python

3.10

### Application package

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-tsingmicro-tsm260610:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-tsingmicro-tsm260610:2.2.0-0.2.2
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  $IMG vllm-serve --model <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.2.0-0.2.2

*2026-09-28 06:57:49*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-20 11:10:59*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and the 0.7.0-era FlagTree, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.1_g90ffdf0.d20260912

*2026-09-13 07:07:04*

Initial vllm 0.20.2 deliverable on tsingmicro TSM 260610 (Tsingmicro TX8110). TX8110 computes the flag_gems attention, rms_norm and rotary_embedding kernels silently wrong, so attention runs through torch SDPA with plain-index KV writes and the other two fall back to reference; the triton copy/cast kernels are blacklisted because they hang on dtype-changing casts during sampling. F/T dual-compiler serve plus inference E2E verified, both paths token-identical on the anchor prompts.
