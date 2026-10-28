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

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g32eabf40e`

## Environment

- `TORCHINDUCTOR_COMPILE_THREADS=1`
- `SGLANG_IS_FLASHINFER_AVAILABLE=false`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`
- `SGLANG_WARMUP_TIMEOUT=3600`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-enflame-tops1.9.10:2.2.0-0.1.dev1_g32eabf40e`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-enflame-tops1.9.10:2.2.0-0.1.dev1_g32eabf40e
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
  $IMG sglang-serve --model-path <path> --port 9000
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
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.2.0-0.1.dev1_g32eabf40e

*2026-09-29 01:53:01*

Rebuild on the FlagOS 2.2.0 stack and the enflame runtime rebuilt on FlagTree 0.7.0 (0.6.0/0.7.0rc2 → 0.7.0+enflame3.6, 2026-09-28). Same sglang and plugin pins as the 2.1.2 image it replaces (PR 91 head, still open).

### 2.1.2-0.1.dev1_g32eabf40e

*2026-09-06 15:10:15*

sglang 0.5.18 on enflame tops1.9.10. sglang-plugin-FL PR 91: revive vendor layer + fix serve.
