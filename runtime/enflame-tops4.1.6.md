## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame L600
- **Host driver:** 4.1.6
- **Container toolkit** *(optional)*: tencent-container-toolkit >= 2.0.52

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops4.1.6:2.3.0`

### Python

3.12

### Major Python packages

- `flag_gems==5.4.0`
- `flagcx==0.14.1+tops4.1.6`
- `flagtree==0.7.1+enflame3.6`
- `numpy==1.26.4`
- `pyefml==4.1.6`
- `topstx==4.1.6`
- `torch-gcu==2.13.0+4.1.20261110`
- `torch==2.13.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.28.0+cpu`
- `triton==3.6.0 (+ triton-gcu==3.6.0+1.0.20261116)` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

### Choosing a FlagTree version

To use a FlagTree version other than the one above, pass `-e FLAGTREE_VERSION=<version>` to `docker run`, or run `compiler flagtree <version>` in a running container: the wheel is installed into `/opt/flagtree` before the application starts, so no rebuild is needed. Write the full `0.7.1+enflame3.6` form to pin one build.

### Choosing a FlagGems version

Pass `-e FLAGGEMS_VERSION=<version>` to `docker run` to install that FlagGems release before the application starts — no rebuild. `-e FLAGGEMS_VERSION=latest` takes the newest build on the **daily** line instead, which leads the next release; it is the newest on that line, not the newest compared to what the image already carries. The wheel is about 13 MB and is fetched once per container. An in-container install keeps the rest of the stack as built, and a request that cannot be met stops the container rather than starting on a different FlagGems.

## Environment

- `TORCH_GCU_ENABLE_INT64_AND_UINT64=1`
- `ENABLE_I64_CHECK=0`
- `TORCHGCU_INDUCTOR_ENABLE=1`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops4.1.6:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops4.1.6:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```

## Changelog

### 2.3.0

*2026-11-18 06:41:31*

- First delivery: the runtime for Enflame tops4.1.6 (L600), built on the
  flagos-base-enflame-tops4.1.6:2.3.0 base. Deps pin
  torch-gcu==2.13.0+4.1.20261110, pyefml==4.1.6, flagcx==0.14.1+tops4.1.6
  and FlagTree 0.7.1 with the Triton fallback.
- `ENFLAME_PT_OP_DEBUG_CONFIG=fallback_cpu=all_ops` is not set in the
  image environment.
