## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.3.0-server

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.3.0:2.3.0`

### Python

3.12

### Major Python packages

- `flag_gems==5.4.0`
- `flagcx==0.14.1+musa5.3.0`
- `flagtree==0.7.0+mthreads3.6`
- `mkl==2024.0.0`
- `numpy==1.26.4`
- `torch==2.13.0.post1+musa20261110`
- `torch_musa==2.13.0.post1+musa20261110`
- `torchaudio==2.11.0.post2+musa20261110`
- `torchvision==0.28.0.post1+musa5.3.0`
- `triton-musa==3.6.0+musa5.3.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

### Choosing a FlagTree version

To use a FlagTree version other than the one above, pass `-e FLAGTREE_VERSION=<version>` to `docker run`, or run `compiler flagtree <version>` in a running container: the wheel is installed into `/opt/flagtree` before the application starts, so no rebuild is needed. Write the full `0.7.0+<backend>3.6` form to pin one build.

### Choosing a FlagGems version

Pass `-e FLAGGEMS_VERSION=<version>` to `docker run` to install that FlagGems release before the application starts — no rebuild. `-e FLAGGEMS_VERSION=latest` takes the newest build on the **daily** line instead, which leads the next release; it is the newest on that line, not the newest compared to what the image already carries. The wheel is about 13 MB and is fetched once per container. An in-container install keeps the rest of the stack as built, and a request that cannot be met stops the container rather than starting on a different FlagGems.

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.3.0:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```

## Changelog

### 2.3.0

*2026-11-15 10:01:14*

- First mthreads 5.3.0 runtime image: the MUSA 5.3.0 base plus the python
  3.12 venv, torch 2.13.0.post1+musa20261110, torch_musa, torchaudio
  2.11.0.post2, torchvision 0.28.0.post1+musa5.3.0, mkl 2024.0.0 and
  numpy 1.26.4, with FlagGems 5.4.0.
- FlagTree `0.7.0+mthreads3.6` joins the vendor triton, as the default
  compiler.
- `flagcx 0.14.1+musa5.3.0` is pinned in deps:, so FlagTree resolves
  libflagcx.so to the package's copy rather than the one triton/_C
  bundles.
