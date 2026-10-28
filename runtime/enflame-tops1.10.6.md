## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.10.6
- **Container toolkit** *(optional)*: tencent-container-toolkit >= 2.0.52

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.10.6:2.2.0`

### Python

3.12

### Major Python packages

- `enflame-modelopt==3.6.20260615+torch.2.11.0`
- `flag_gems==5.4.0`
- `flagtree==0.7.0rc2+enflame3.6`
- `flash-attn==2.7.2+torch.2.11.0.gcu.3.8.20260706`
- `numpy==1.26.4`
- `pyefml==1.10.6`
- `tops-extension==3.6.20260529+torch.2.11.0`
- `topstx==1.10.6`
- `torch-gcu==2.11.0+3.8.20260713`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchcodec==3.8.20260624+torch.2.11.0`
- `torchvision==0.26.0+cpu`
- `triton==3.6.0 (+ triton-gcu==3.6.0+1.0.20260722)` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Environment

- `TORCH_GCU_ENABLE_INT64_AND_UINT64=1`
- `ENABLE_I64_CHECK=0`
- `TORCHGCU_INDUCTOR_ENABLE=1`
- `ENFLAME_PT_OP_DEBUG_CONFIG=fallback_cpu=all_ops`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.10.6:2.2.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.10.6:2.2.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```

## Changelog

### 2.3.0

*2026-10-25 09:57:55*

This image gains the container-start version request: `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>` override the versions baked in, resolved from the image's own indexes before the application starts. `latest` takes the newest wheel on the daily line. A request that cannot be honoured stops the container with a non-zero exit rather than letting it run on a different version. The image bakes the files those requests read, among them the constraints file that holds an in-container FlagGems install to this image's own pins.

*2026-10-23 03:52:57*

flagcx 0.14.0 becomes a runtime dependency on this backend: configs.yaml deps: now pins flagcx==0.14.0+tops1.10.6, so the DEPS install pulls it from the vendor index and FlagTree resolves libflagcx.so to the package's copy instead of the one triton/_C bundles. Nothing else about the image changes.

*2026-10-17 00:28:45*

This image first carried the FlagTree version override (build-infra #1342, merged 2026-10-14): zz-flagos.sh now honours a FlagTree version requested at container start (`docker run -e FLAGTREE_VERSION=<ver>`), and `compiler flagtree <ver>` does the same in a running container. The requested wheel is installed into /opt/flagtree in place -- fetched from this image's own vendor index (/etc/flagos/vendor-index, written at build time), with the shared lane as a sequential second attempt -- so a FlagTree bump no longer forces a rebuild of this image and of every app image above it. A failed install warns and leaves the baked compiler active. Recorded late: this push is older than the entry above it, and its date is the push that first carried the override.
