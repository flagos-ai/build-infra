## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.52

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.7.6:2.3.0`

### Python

3.12

### Major Python packages

- `cncv==2.12.1`
- `flag_gems==5.4.0`
- `flagcx==0.14.1+neuware4.7.6`
- `numpy==1.26.4`
- `pandas==3.0.5`
- `torch-mlu-ops==1.13.0+torch2.13.0`
- `torch-mlu==1.34.1+torch2.13.0`
- `torch==2.13.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.28.0+cpu`
- `triton==3.4.0+mlu2.1.3`

### Choosing a FlagGems version

Pass `-e FLAGGEMS_VERSION=<version>` to `docker run` to install that FlagGems release before the application starts — no rebuild. `-e FLAGGEMS_VERSION=latest` takes the newest build on the **daily** line instead, which leads the next release; it is the newest on that line, not the newest compared to what the image already carries. The wheel is about 13 MB and is fetched once per container. An in-container install keeps the rest of the stack as built, and a request that cannot be met stops the container rather than starting on a different FlagGems.

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.6:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```

## Changelog

### 2.3.0

*2026-11-19 08:58:22*

- First delivery: the Neuware 4.7.6 runtime, built on
  `flagos-base-cambricon-neuware4.7.6` with python 3.12 and the torch
  2.13.0 stack — torch 2.13.0+cpu, torch-mlu 1.34.1+torch2.13.0,
  torch-mlu-ops 1.13.0+torch2.13.0, torchvision 0.28.0+cpu and
  torchaudio 2.11.0+cpu — plus cncv 2.12.1.
- The vendor Triton is 3.4.0+mlu2.1.3, the build matched to this SDK.
  This line has no FlagTree, so Triton is the only compiler installed and
  the `compiler` toggle has nothing to switch to.
- flagcx 0.14.1+neuware4.7.6 is a runtime dependency: FlagTree prefers the
  package's libflagcx.so over the copy triton/_C bundles, so the pin
  rides `deps:` like it does on 4.7.2.
