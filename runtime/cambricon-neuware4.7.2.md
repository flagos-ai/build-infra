## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.48

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.7.2:2.2.0`

### Python

3.12

### Major Python packages

- `flag_gems==5.4.0`
- `numpy==1.26.4`
- `pandas==3.0.5`
- `torch-mlu-ops==1.12.1+torch2.11.0`
- `torch-mlu==1.33.1+torch2.11.0`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- `triton==3.4.0+mlu2.1.1`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.2:2.2.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```

## Changelog

### 2.3.0

*2026-10-25 09:45:41*

This image gains the container-start version request: `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>` override the versions baked in, resolved from the image's own indexes before the application starts. `latest` takes the newest wheel on the daily line. A request that cannot be honoured stops the container with a non-zero exit rather than letting it run on a different version. The image bakes the files those requests read, among them the constraints file that holds an in-container FlagGems install to this image's own pins.

*2026-10-23 03:45:54*

flagcx 0.14.0 becomes a runtime dependency on this backend: configs.yaml deps: now pins flagcx==0.14.0+neuware4.7.2, so the DEPS install pulls it from the vendor index and FlagTree resolves libflagcx.so to the package's copy instead of the one triton/_C bundles. Nothing else about the image changes.

*2026-10-17 00:22:58*

This image first carried the FlagTree version override (build-infra #1342, merged 2026-10-14): zz-flagos.sh now honours a FlagTree version requested at container start (`docker run -e FLAGTREE_VERSION=<ver>`), and `compiler flagtree <ver>` does the same in a running container. The requested wheel is installed into /opt/flagtree in place -- fetched from this image's own vendor index (/etc/flagos/vendor-index, written at build time), with the shared lane as a sequential second attempt -- so a FlagTree bump no longer forces a rebuild of this image and of every app image above it. A failed install warns and leaves the baked compiler active. Recorded late: this push is older than the entry above it, and its date is the push that first carried the override.
