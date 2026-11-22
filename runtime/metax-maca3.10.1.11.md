## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.100.1
- **Container toolkit** *(optional)*: metax-docker >= 0.15.3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.10.1.11:2.3.0`

### Python

3.12

### Major Python packages

- `apex==0.1+metax3.10.1.3torch2.13`
- `flag_gems==5.4.0`
- `flagcx==0.14.1+maca3.10.1.11`
- `flagtree==0.7.0+metax3.6`
- `flash_attn==2.6.3+metax3.10.1.3torch2.13`
- `flash_linear_attention==0.5.0+metax3.10.1.3torch2.13`
- `flash_mla==1.0.1+metax3.10.1.3torch2.13`
- `flashinfer==0.2.6+metax3.10.1.3torch2.13`
- `numpy==1.26.4`
- `torch==2.13.0+metax3.10.1.3`
- `torchaudio==2.4.1+metax3.10.1.3torch2.13`
- `torchcodec==0.6.0+metax3.10.1.3torch2.13`
- `torchvision==0.25.0+metax3.10.1.3torch2.13`
- `triton==3.6.0+metax3.10.1.3torch2.13` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

### Choosing a FlagTree version

To use a FlagTree version other than the one above, pass `-e FLAGTREE_VERSION=<version>` to `docker run`, or run `compiler flagtree <version>` in a running container: the wheel is installed into `/opt/flagtree` before the application starts, so no rebuild is needed. Write the full `0.7.0+metax3.6` form to pin one build.

### Choosing a FlagGems version

Pass `-e FLAGGEMS_VERSION=<version>` to `docker run` to install that FlagGems release before the application starts — no rebuild. `-e FLAGGEMS_VERSION=latest` takes the newest build on the **daily** line instead, which leads the next release; it is the newest on that line, not the newest compared to what the image already carries. The wheel is about 13 MB and is fetched once per container. An in-container install keeps the rest of the stack as built, and a request that cannot be met stops the container rather than starting on a different FlagGems.

## Environment

- `USE_FLAGTUNE_COST_MODEL=0`

## Launch

**With the container toolkit** *(optional)*:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.10.1.11:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.10.1.11:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```

## Changelog

### 2.3.0

*2026-11-22 12:29:35*

- Rebuilt on the metax-maca3.10.1.11 base that now carries libjpeg-turbo8
  and libpng16-16t64 (#1944). The MetaX torchvision wheel links those
  system sonames rather than vendored copies, so without them
  torchvision.io PNG/JPEG codecs were unavailable. Nothing else about
  this layer changes.

*2026-11-18 12:32:51*

- First delivery: the runtime for MetaX MACA 3.10.1.11 (C550), built on
  the flagos-base-metax-maca3.10.1.11:2.3.0 base. Deps pin torch 2.13.0,
  apex, torchcodec, torchaudio, torchvision, flash_attn, flashinfer,
  flash_linear_attention and flash_mla from the vendor's 3.10.1.3 wheel
  line, plus flagcx 0.14.1+maca3.10.1.11.
- Ships FlagTree 0.7.0 with Triton 3.6.0 as the side install. The FlagTune
  cost model is off: a partial flagtune puts its errors outside the
  fallback set, aborting the operator instead of degrading.
- mcoplib is deliberately absent: its `_C` extension registers
  TORCH_LIBRARY(_C) exactly as vllm_fl._C does, so a process importing
  both aborts at plugin load.
