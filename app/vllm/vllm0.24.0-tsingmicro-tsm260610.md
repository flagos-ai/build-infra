## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Tsingmicro TX8110
- **Host driver:** 260610164501.01
- **Container toolkit** *(optional)*: tx-container-toolkit >= 2.5.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm260610:2.3.0`

### Python

3.10

### Application package

`vllm==0.24.0+flagos`


`vllm-plugin-fl==0.3.0`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-tsingmicro-tsm260610:2.3.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-tsingmicro-tsm260610:2.3.0-0.3.0
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

### 2.3.0-0.3.0

*2026-10-26 13:02:36*

- The runtime introduces two container-start flags,
  `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>`,
  which override the compiler and FlagGems versions baked into the image. A
  request that cannot be honoured stops the container instead of letting it
  run on another version.
- flagcx 0.14.0 is now a runtime dependency, pinned as
  flagcx==0.14.0+tsm260610.

### 2.2.0-0.3.0

*2026-09-28 14:41:28*

The 0.24.0 line moves to the vllm-plugin-FL formal release v0.3.0 (tag = commit f105277). The plugin now ships as the release version (vllm-plugin-fl==0.3.0, one py3-none-any wheel, sha adf5a9e3...451f62, on every vendor index) instead of the v0.3.0-rc2.post2 delivery tag. Same stack and app pins as the rc2.post2 image it replaces; the only delta is the formal release of the same code.

### 2.2.0-0.3.0rc2.post2

*2026-09-20 10:31:16*

The txda enablement (PR 460) is on the release line now, so this image leaves 2f034ee, the 0.3.0-rc0-based build of it. Rebuilt on the FlagOS 2.2.0 stack, whose base and runtime carry FlagGems 5.4.0-rc2.post3, and on the vllm-plugin- FL release tag v0.3.0-rc2.post2 (0891073, head of 0.3.0-rc2): the plugin comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.3.0rc0_g2f034ee.d20260908

*2026-09-08 12:22:01*

Enable vllm 0.24.0 on tsingmicro via vllm-plugin-FL PR 460 (tsingmicro-enable-main). The PR 447 txda skeleton is not independently serveable (init nccl crash, warmup generator crash, wrong attention/norms routing); this build adds the minimal enablement: txda->tccl dist backend, cpu torch.Generator, tsingmicro.yaml (norms reference-first, attention->vendor/TxdaSDPA), TxdaSDPAAttentionBackend. F/T both serve 5/5 correct. Supersedes the PR 421-based deliverable (bd010ce), whose KV-write-gate and SDPA-attention work is carried forward.
