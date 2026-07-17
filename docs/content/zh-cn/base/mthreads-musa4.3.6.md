---
title: "mthreads-musa4.3.6"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** MThreads MTT S5000
- **宿主机驱动:** 5.2.0-server
- **容器工具包** *(可选 —— 仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装)*: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## 镜像内容

### 基础镜像

`ubuntu:24.04`

### 系统软件包

显式安装；此处版本即为该镜像中实际打包的版本：

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `libelf1`
- `libgfortran5`
- `libnuma-dev`
- `libopenmpi-dev`
- `libpython3-dev`
- `openmpi-bin`

### SDK 组件

- MUSA Toolkits RC4.3.6
- MCCL RC2.1.6
- muDNN RC3.1.6

## 环境变量

- `MUSA_HOME=/usr/local/musa`
- `PATH=/usr/local/musa/bin:${PATH}`
- `LD_LIBRARY_PATH=/usr/local/musa/lib`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa4.3.6:2.1.1-20-g18451ed bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa4.3.6:2.1.1-20-g18451ed bash
```

## 验证

在容器内，确认加速器可见：

```bash
mthreads-gmi
```
