## Prerequisites

- **Architecture:** x86_64
- **Chip models:** AMD Radeon PRO W7900
- **Host driver:** 6.16.13
- **Container toolkit** *(optional)*: amd-container-toolkit >= 1.3.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-amd-rocm7.2.4:2.3.0`

### Python

3.12

### Major Python packages

- `flag_gems==5.4.0`
- `flagcx==0.14.1+rocm7.2.4`
- `flagtree==0.7.0+amd3.6`
- `numpy==1.26.4`
- `torch==2.11.0+rocm7.2`
- `torchaudio==2.11.0+rocm7.2`
- `torchvision==0.26.0+rocm7.2`
- `triton-rocm==3.6.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

### Choosing a FlagTree version

To use a FlagTree version other than the one above, pass `-e FLAGTREE_VERSION=<version>` to `docker run`, or run `compiler flagtree <version>` in a running container: the wheel is installed into `/opt/flagtree` before the application starts, so no rebuild is needed. Write the full `0.7.0+<backend>3.6` form to pin one build.

### Choosing a FlagGems version

Pass `-e FLAGGEMS_VERSION=<version>` to `docker run` to install that FlagGems release before the application starts — no rebuild. `-e FLAGGEMS_VERSION=latest` takes the newest build on the **daily** line instead, which leads the next release; it is the newest on that line, not the newest compared to what the image already carries. The wheel is about 13 MB and is fetched once per container. An in-container install keeps the rest of the stack as built, and a request that cannot be met stops the container rather than starting on a different FlagGems.

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime amd \
  --device /dev/kfd \
  --device /dev/dri \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-amd-rocm7.2.4:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/dri \
  --group-add video \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-amd-rocm7.2.4:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
rocm-smi
```

## Changelog

### 2.3.0

*2026-10-31 13:13:04*

Rebuilt on the corrected base image: the `HIP_VISIBLE_DEVICES=all` ENV is gone, so this image now enumerates every GPU out of the box instead of zero. HIP 7.2 takes ordinals or GPU-UUIDs only, and the base image had been setting the NVIDIA-style `all`, which parsed to an empty device list: `torch.cuda.device_count()` returned 0 while `rocm-smi` listed every card. No package, compiler or version changes — the venv and the flagcx dependency are the same as the previous push.

*2026-10-31 09:25:08*

flagcx 0.14.1 becomes a runtime dependency on this backend: configs.yaml deps: now pins flagcx==0.14.1+rocm7.2.4, so the DEPS install pulls it from the vendor index and FlagTree resolves libflagcx.so to the package's copy instead of the one triton/_C bundles. Nothing else about the image changes.

*2026-10-27 10:04:40*

This image's base gains the hipsolver, hipfft and miopen-hip development packages. torch's headers include theirs under USE_ROCM, and the flagcx torch wheel compiles against them in this image, so the three are required for the wheel build to succeed.

*2026-10-27 06:29:51*

First release of this backend's runtime image. It layers the ROCm torch closure — torch 2.11.0+rocm7.2, torchvision 0.26.0+rocm7.2, torchaudio 2.11.0+rocm7.2, numpy 1.26.4 — and the ROCm triton 3.6.0 that ships the amd backend, alongside FlagTree 0.7.0+amd3.6 and FlagGems 5.4.0 on the base image (ROCm 7.2.4, gfx1100).
