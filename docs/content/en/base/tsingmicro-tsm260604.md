---
title: "tsingmicro-tsm260604"
---

`harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1`

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Tsingmicro TX8110

## System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `clang` — 14.0
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `libfmt-dev` — 8.1.1+ds1
- `libopenmpi3` — 4.1.2
- `libpython3-dev` — 3.10.6
- `libunwind8` — 1.3.2
- `sudo` — 1.9.9

## SDK components

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

Start an interactive shell in the container:

```bash
docker run --rm -it --privileged --ipc=host -v /dev:/dev -v /lib/modules:/lib/modules harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible (the first run may take a moment):

```bash
tsm-smi
```
