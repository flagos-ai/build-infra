---
title: "tsingmicro-tsm260604"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Tsingmicro TX8110
- **Host driver:** 260604163331.01
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: tx-container-toolkit >= 2.5.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `clang`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `libfmt-dev`
- `libopenmpi3`
- `libpython3-dev`
- `libunwind8`
- `sudo`

### SDK components

- TSM Runtime 260604163331
- TSM Validation Suite 260604163331
- TSM CCL 260604163331
- TSM Profiler 260604163331
- TX8 Compiler Dependencies 20260507
- LLVM a66376b0

## Environment

- `KUIPER_PATH=/usr/local/kuiper`
- `TX8_DEPS_ROOT=/usr/local/tx8_deps`
- `LLVM_SYSPATH=/usr/local/llvm`
- `PATH=/usr/local/kuiper/bin:${PATH}`
- `LLVM_BINARY_DIR=/usr/local/llvm/bin`
- `PYTHONPATH=/usr/local/llvm/python_packages/mlir_core`
- `LD_LIBRARY_PATH=/usr/local/tx8_deps/lib:/usr/local/kuiper/lib:/usr/local/kuiper/tsm8-profiler/lib`
- `USE_TORCH_XLA=0`
- `TORCH_COMPILE_DISABLE=1`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1-21-g7fe5cbd bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1-21-g7fe5cbd bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
tsm_smi
```
