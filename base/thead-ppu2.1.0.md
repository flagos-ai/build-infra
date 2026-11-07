## Prerequisites

- **Applicable platform:** Aliyun PAI-DSW
- **Architecture:** x86_64
- **Chip models:** T-Head ZW810E
- **Host driver:** 2.0.0

## Image contents

### Base image

`youyu-registry.cn-wulanchabu.cr.aliyuncs.com/train/torch:pai-dsw`

### System packages

Explicitly installed; the version is the one baked into this image:

- `cmake` — 3.28.3
- `libpython3-dev` — 3.12.3

### SDK components

- PPU SDK 2.1.0 (x86_64)

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --privileged \
  --shm-size=512g \
  --ipc host \
  --network host \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-base/flagos-base-thead-ppu2.1.0:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ppu-smi
```

*Last updated: 2026-11-07 10:31:44 · `2b51e8a5d0bd`*

## Changelog

### 2.3.0

*2026-11-07 02:41:49*

- First delivery: T-Head PPU 2.1.0 on Ubuntu 24.04, x86_64.
- The layer is vendored, not installed: T-Head ships the PPU SDK only
  inside their PAI-DSW training image, so this base takes that image and
  drops its platform entrypoint (`/home/pai/bin/entrypoint`, a DSW
  harness). There is no installer package and nothing on the filestore
  to build from.
- Carries PPU_SDK v2.1.0 at `/usr/local/PPU_SDK` (ppu-smi, the
  CUDA-compat headers, HGGC 13.3) and deliberately no torch/triton — the
  runtime venv owns the whole Python stack, as on every other backend.
- Adds the two things the vendor image lacks for our purposes: cmake +
  libpython3-dev, and a pip index pointed at the stack mirror instead of
  the vendor's PAI platform endpoint.
