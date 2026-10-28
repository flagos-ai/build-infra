## Prerequisites

- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host driver:** 610.43.02
- **Container toolkit** *(optional)*: nvidia-container-toolkit

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.3:2.2.0`

### Python

3.12

### Major Python packages

- `flag_gems==5.4.0`
- `flagcx==0.14.0rc2.post2+cuda13.3`
- `flagtree==0.7.0`
- `numpy==1.26.4`
- `torch==2.11.0+cu130`
- `torchaudio==2.11.0+cu130`
- `torchvision==0.26.0+cu130`
- `triton==3.6.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Environment

- `USE_FLAGTUNE_COST_MODEL=0`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:2.2.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:2.2.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
nvidia-smi
```

## Changelog

### 2.3.0

*2026-10-25 09:46:58*

This image gains the container-start version request: `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>` override the versions baked in, resolved from the image's own indexes before the application starts. `latest` takes the newest wheel on the daily line. A request that cannot be honoured stops the container with a non-zero exit rather than letting it run on a different version. The image bakes the files those requests read, among them the constraints file that holds an in-container FlagGems install to this image's own pins.

*2026-10-23 03:45:50*

The flagcx wheel this image carries has been replaced since it was pushed (2026-10-17 00:31 UTC): the wheel build that ran before it failed on exactly these two nvidia rows and was re-dispatched, and the re-upload differs in size from the artifact this build downloaded. Rebuilt with no_cache=true so the DEPS layer re-downloads flagcx==0.14.0+cuda13.3 instead of reusing the cached layer -- an unchanged pin at the same version is exactly what the build cache hides.

*2026-10-17 00:31:29*

This image first carried the FlagTree version override (build-infra #1342, merged 2026-10-14): zz-flagos.sh now honours a FlagTree version requested at container start (`docker run -e FLAGTREE_VERSION=<ver>`), and `compiler flagtree <ver>` does the same in a running container. The requested wheel is installed into /opt/flagtree in place -- fetched from this image's own vendor index (/etc/flagos/vendor-index, written at build time), with the shared lane as a sequential second attempt -- so a FlagTree bump no longer forces a rebuild of this image and of every app image above it. A failed install warns and leaves the baked compiler active. Recorded late: this push is older than the entry above it, and its date is the push that first carried the override.
