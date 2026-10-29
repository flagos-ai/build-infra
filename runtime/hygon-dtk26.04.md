## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.3.0`

### Python

3.10

### Major Python packages

- `apex==1.7.0+das.opt1.dtk2604.torch290`
- `flag_gems==5.4.0`
- `flagcx==0.14.0+dtk2604`
- `flagtree==0.7.0+hcu3.6`
- `flash_attn==2.8.3+das.opt1.dtk2604.torch290`
- `numpy==1.26.4`
- `torch==2.9.0+das.opt1.dtk2604`
- `torchvision==0.24.0+das.opt1.dtk2604.torch290`
- `triton==3.5.1+das.opt1.dtk2604.torch290` *(alternative)*

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
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
hy-smi
```

## Changelog

### 2.3.0

*2026-10-27 03:24:06*

The base image gains libgoogle-glog0v6t64. The vllm-plugin-FL native build (0.3.0+dtk26.4) links libglog.so.1 — torch's c10 headers pull glog in at compile time — and this vendor's SDK ships no such soname, so the plugin's `vllm_fl._C` failed to import and the app image could not serve. Nothing else about the image changes.

*2026-10-25 09:46:37*

This image gains the container-start version request: `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>` override the versions baked in, resolved from the image's own indexes before the application starts. `latest` takes the newest wheel on the daily line. A request that cannot be honoured stops the container with a non-zero exit rather than letting it run on a different version. The image bakes the files those requests read, among them the constraints file that holds an in-container FlagGems install to this image's own pins. On the vendor bases whose SDK env assigns PATH absolutely (ascend, hygon), the profile plumbing also re-asserts the venv prefix after that assignment: `pip` was otherwise resolving to the system interpreter, or to none, before the request could run.

*2026-10-23 03:50:32*

flagcx 0.14.0 becomes a runtime dependency on this backend: configs.yaml deps: now pins flagcx==0.14.0+dtk2604, so the DEPS install pulls it from the vendor index and FlagTree resolves libflagcx.so to the package's copy instead of the one triton/_C bundles. Nothing else about the image changes.

*2026-10-17 00:32:31*

This image first carried the FlagTree version override (build-infra #1342, merged 2026-10-14): zz-flagos.sh now honours a FlagTree version requested at container start (`docker run -e FLAGTREE_VERSION=<ver>`), and `compiler flagtree <ver>` does the same in a running container. The requested wheel is installed into /opt/flagtree in place -- fetched from this image's own vendor index (/etc/flagos/vendor-index, written at build time), with the shared lane as a sequential second attempt -- so a FlagTree bump no longer forces a rebuild of this image and of every app image above it. A failed install warns and leaves the baked compiler active. Recorded late: this push is older than the entry above it, and its date is the push that first carried the override.
