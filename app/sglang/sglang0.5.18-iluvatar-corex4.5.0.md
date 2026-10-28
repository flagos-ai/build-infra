## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.5.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.5.0:2.2.0`

### Python

3.12

### Application package

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g201484665`

## Environment

- `TORCHINDUCTOR_COMPILE_THREADS=1`
- `SGLANG_IS_FLASHINFER_AVAILABLE=false`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-iluvatar-corex4.5.0:2.2.0-0.1.dev1_g201484665`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-iluvatar-corex4.5.0:2.2.0-0.1.dev1_g201484665
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

### 2.2.0-0.1.dev1_g201484665

*2026-09-23 11:33:09*

First rebuild since the stack moved to 2.2.0, so the tag leaves 2.1.2. The base and runtime underneath are new for two reasons: the CoreX cmake installer was being handed a flag it silently ignores, leaving every image in the chain with a cmake that cannot run (#1011), and FlagGems moves to the version this stack pins. Same sglang and plugin pins as the 2.1.2 image it replaces.

### 2.1.2-0.1.dev1_g201484665

*2026-09-10 11:59:36*

sglang 0.5.18 on iluvatar CoreX 4.5.0. corex torch is CUDA-alias, so sglang's is_cuda() is true while the platform has neither an NVIDIA device nor the NVIDIA-only packages its CUDA paths expect: the plugin branch closes the four resulting gaps (flashinfer import face via an on-disk stub package, the sm75 dtype floor, the nvcc-JIT clamp_position, and vendor triton 3.2 missing the PDL intrinsics). F/T dual-compiler E2E verified on Qwen3-4B.
