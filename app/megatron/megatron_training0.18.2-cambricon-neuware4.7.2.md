## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.48

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.2:2.2.0`

### Python

3.12

### Application package

`megatron-core[training]==0.18.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.18.2-cambricon-neuware4.7.2:2.2.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.18.2-cambricon-neuware4.7.2:2.2.0-0.3.0
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
  $IMG megatron-train --model-type GPT
```
