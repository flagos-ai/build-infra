## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 5.0.1
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex5.0.1:2.3.0`

### Python

3.12

### Application package

`vllm==0.32.0+flagos`


`vllm-plugin-fl==0.5.0.dev0+g814b6d3.d20261117`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.32.0-iluvatar-corex5.0.1:2.3.0-0.5.0.dev0_g814b6d3.d20261117`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.32.0-iluvatar-corex5.0.1:2.3.0-0.5.0.dev0_g814b6d3.d20261117
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

### 2.3.0-0.5.0.dev0_g814b6d3.d20261117

*2026-11-17 11:28:21*

- First vllm 0.32.0 app image on iluvatar-corex5.0.1, FlagGems 5.4.0, FlagTree 0.7.1a1+iluvatar3.6 (FlagOS 2.3.0 stack).
- Installs the pure-Python plugin wheel `0.5.0.dev0+g814b6d3.d20261117` (commit 814b6d3 on the vllm-plugin-FL 0.5.0-dev branch).
- Adds `flaggems_vllm==0.3.0.dev20261117` as an app-layer dependency:
  the 0.5.0-dev plugin's FlagGems backend imports it for its core ops
  (silu/gelu/rotary/moe/attention/mla) and does not declare it.
