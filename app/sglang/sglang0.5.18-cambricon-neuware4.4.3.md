## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.2.15

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.4.3:2.1.2`

### Python

3.10

### Application package

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g0b9d98a78`

## Environment

- `TORCHINDUCTOR_COMPILE_THREADS=1`
- `SGLANG_IS_FLASHINFER_AVAILABLE=false`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`
- `SGLANG_WATCHDOG_TIMEOUT=900`
- `SGLANG_WARMUP_TIMEOUT=1800`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-cambricon-neuware4.4.3:2.1.2-0.1.dev1_g0b9d98a78`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-cambricon-neuware4.4.3:2.1.2-0.1.dev1_g0b9d98a78
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
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.1.2-0.1.dev1_g0b9d98a78

*2026-09-07 03:56:26*

sglang 0.5.18 on cambricon neuware4.4.3. sglang-plugin-FL PR 90: MLU vendor patches (cold-start watchdog baked per cambricon cold-start record).
