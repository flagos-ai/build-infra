## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 26.1.1
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.2.1:2.3.0`

### Python

3.12

### Major Python packages

- `cann-shmem==1.6.0`
- `flag_gems==5.4.0`
- `flagcx==0.14.1+cann9.2.1`
- `flagtree==0.7.1a1+ascend3.5`
- `numpy==1.26.4`
- `torch-npu==2.13.0`
- `torch==2.13.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.28.0+cpu`
- `triton==3.6.0 (+ triton_ascend==3.6.0)` *(alternative)*

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
  --privileged \
  --shm-size=1g \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann9.2.1:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --shm-size=1g \
  --device /dev/davinci0 \
  --device /dev/davinci1 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann9.2.1:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
npu-smi info
```

## Changelog

### 2.3.0

*2026-11-04 07:42:15*

flagcx 0.14.1+cann9.2.1 becomes a runtime dependency on this backend: configs.yaml deps: now pins flagcx==0.14.1+cann9.2.1, so the DEPS install pulls it from the vendor index and FlagTree resolves libflagcx.so to the package's copy instead of the one triton/_C bundles. Nothing else about the image changes.

*2026-11-04 06:08:40*

- First delivery of this backend's runtime image. It layers the python 3.12
  torch closure — torch 2.13.0+cpu, torch-npu 2.13.0, torchvision 0.28.0
  and torchaudio 2.11.0 — plus numpy 1.26.4 and cann-shmem 1.6.0, with
  FlagGems 5.4.0, on the CANN 9.2.1 base image.
- FlagTree is the default compiler, at 0.7.1a1+ascend3.5 — the published
  ascend build that matches python 3.12. It carries the AscendNPU-IR
  v1.2.x pin rather than one matched to this CANN's bishengir 2.0.0, a
  mismatch measured as no regression across the vllm-critical op set.
- triton 3.6.0 with its triton_ascend 3.6.0 overlay installs beside it in
  /opt/triton as the vendor fallback, switched with `compiler triton`.
