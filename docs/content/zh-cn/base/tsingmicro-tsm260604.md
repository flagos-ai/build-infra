---
title: "tsingmicro-tsm260604"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Tsingmicro TX8110
- **宿主机驱动:** 260604163331.01
- **容器工具包** <abbr title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">*(可选)*</abbr>: tx-container-toolkit >= 2.5.0

## 镜像内容

### 基础镜像

`ubuntu:24.04`

### 系统软件包

显式安装；此处版本即为该镜像中实际打包的版本：

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

### SDK 组件

- TSM Runtime 260604163331
- TSM Validation Suite 260604163331
- TSM CCL 260604163331
- TSM Profiler 260604163331
- TX8 Compiler Dependencies 20260507
- LLVM a66376b0

## 环境变量

- `KUIPER_PATH=/usr/local/kuiper`
- `TX8_DEPS_ROOT=/usr/local/tx8_deps`
- `LLVM_SYSPATH=/usr/local/llvm`
- `PATH=/usr/local/kuiper/bin:${PATH}`
- `LLVM_BINARY_DIR=/usr/local/llvm/bin`
- `PYTHONPATH=/usr/local/llvm/python_packages/mlir_core`
- `LD_LIBRARY_PATH=/usr/local/tx8_deps/lib:/usr/local/kuiper/lib:/usr/local/kuiper/tsm8-profiler/lib`
- `USE_TORCH_XLA=0`
- `TORCH_COMPILE_DISABLE=1`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1-20-g9ab46c9 bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1-20-g9ab46c9 bash
```

## 验证

在容器内，确认加速器可见：

```bash
tsm_smi
```
