## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.2.0`

### Python

3.12

### Major Python packages

- `flag_gems==5.4.0`
- `flagtree==0.7.0+iluvatar3.6`
- `numpy==1.26.4`
- `torch==2.7.1+corex.4.4.0`
- `torchaudio==2.7.1+corex.4.4.0`
- `torchvision==0.22.1+corex.4.4.0`
- `triton==3.1.0+corex.4.4.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.2.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  --device /dev/itrctl \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.2.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```

## Changelog

### 2.3.0

*2026-10-25 09:50:49*

This image gains the container-start version request: `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>` override the versions baked in, resolved from the image's own indexes before the application starts. `latest` takes the newest wheel on the daily line. A request that cannot be honoured stops the container with a non-zero exit rather than letting it run on a different version. The image bakes the files those requests read, among them the constraints file that holds an in-container FlagGems install to this image's own pins.

*2026-10-23 03:46:35*

flagcx 0.14.0 becomes a runtime dependency on this backend: configs.yaml deps: now pins flagcx==0.14.0+corex4.4.0, so the DEPS install pulls it from the vendor index and FlagTree resolves libflagcx.so to the package's copy instead of the one triton/_C bundles. Nothing else about the image changes.

*2026-10-14 06:24:03*

This image first carried the FlagTree version override (build-infra #1342, merged 2026-10-14): zz-flagos.sh now honours a FlagTree version requested at container start (`docker run -e FLAGTREE_VERSION=<ver>`), and `compiler flagtree <ver>` does the same in a running container. The requested wheel is installed into /opt/flagtree in place -- fetched from this image's own vendor index (/etc/flagos/vendor-index, written at build time), with the shared lane as a sequential second attempt -- so a FlagTree bump no longer forces a rebuild of this image and of every app image above it. A failed install warns and leaves the baked compiler active. Recorded late: this push is older than the entry above it, and its date is the push that first carried the override.
