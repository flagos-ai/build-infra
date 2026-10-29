## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** *(optional)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.3.0`

### Python

3.10

### Major Python packages

- `flag_gems==5.4.0`
- `flagcx==0.14.0+musa5.2.0`
- `flagtree==0.7.0+mthreads3.6`
- `mkl==2024.0.0`
- `numpy==1.26.4`
- `torch==2.9.1+musa5.2.0`
- `torch_musa==2.9.1`
- `torchaudio==2.9.1+musa5.2.0`
- `torchvision==0.24.1.post1+musa5.2.0`
- `triton==3.6.0` *(alternative)*

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
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```

## Changelog

### 2.3.0

*2026-10-25 09:55:00*

This image gains the container-start version request: `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>` override the versions baked in, resolved from the image's own indexes before the application starts. `latest` takes the newest wheel on the daily line. A request that cannot be honoured stops the container with a non-zero exit rather than letting it run on a different version. The image bakes the files those requests read, among them the constraints file that holds an in-container FlagGems install to this image's own pins.

*2026-10-23 04:24:37*

flagcx 0.14.0 becomes a runtime dependency on this backend: configs.yaml deps: now pins flagcx==0.14.0+musa5.2.0, so the DEPS install pulls it from the vendor index and FlagTree resolves libflagcx.so to the package's copy instead of the one triton/_C bundles. Nothing else about the image changes.

*2026-10-17 00:55:42*

This image first carried the FlagTree version override (build-infra #1342, merged 2026-10-14): zz-flagos.sh now honours a FlagTree version requested at container start (`docker run -e FLAGTREE_VERSION=<ver>`), and `compiler flagtree <ver>` does the same in a running container. The requested wheel is installed into /opt/flagtree in place -- fetched from this image's own vendor index (/etc/flagos/vendor-index, written at build time), with the shared lane as a sequential second attempt -- so a FlagTree bump no longer forces a rebuild of this image and of every app image above it. A failed install warns and leaves the baked compiler active. Recorded late: this push is older than the entry above it, and its date is the push that first carried the override.
