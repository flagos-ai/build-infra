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

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g4d44a24cd`

## Environment

- `TORCHINDUCTOR_COMPILE_THREADS=1`
- `SGLANG_IS_FLASHINFER_AVAILABLE=false`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-iluvatar-corex4.4.0:2.2.0-0.1.dev1_g4d44a24cd`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-iluvatar-corex4.4.0:2.2.0-0.1.dev1_g4d44a24cd
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
  $IMG sglang-serve --model-path <path> --port 9000
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
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.2.0-0.1.dev1_g4d44a24cd

*2026-09-28 13:20:50*

Rebuild on the 4.4.0 runtime with FlagTree downgraded to 0.6.1 (0.7.0 hard-loads libflagcx.so; the CoreX 4.4.0 SDK ships no libixccl, so the runtime failed to import flag_gems). Same stack, sglang and plugin pins as the 0.7.0-era image it replaces.

*2026-09-23 11:33:14*

First rebuild since the stack moved to 2.2.0, so the tag leaves 2.1.2. The base and runtime underneath are new for two reasons: the CoreX cmake installer was being handed a flag it silently ignores, leaving every image in the chain with a cmake that cannot run (#1011), and FlagGems moves to the version this stack pins. Same sglang and plugin pins as the 2.1.2 image it replaces.

### 2.1.2-0.1.dev1_g4d44a24cd

*2026-09-12 11:17:47*

sglang 0.5.18 on Iluvatar CoreX 4.4.0. First image for this backend, whose SDK pins torch 2.7.1 — below what sglang 0.5.18 assumes. Two torch surfaces it imports at startup exist only from 2.8 and neither is reachable from a plugin, because the scheduler worker imports them before any plugin loads: the torch.cuda.memory allocator entry points torch renamed (the caller itself switches between the two spellings by version), and torch.distributed._symmetric_memory, an NVLink multicast all-gather this platform never runs. The torch-compat-shim addon supplies both from interpreter start. Separately, the PDL no-op the plugin injects for the vendor triton had to answer triton 3.1.0's own call check, which asserts where 3.2 only tests — a defect on our side that the newer SDK never exposed. F/T dual-compiler serve verified on Qwen3-4B.
