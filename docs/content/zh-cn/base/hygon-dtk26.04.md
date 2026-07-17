---
title: "hygon-dtk26.04"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Hygon BW1000
- **宿主机驱动:** 6.3.30-V1.4.1a
- **容器工具包** *(可选 —— 仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装)*: dcu-container-toolkit >= 1.3.0

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
- `pciutils`

### SDK 组件

- Hygon DTK 26.04

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1-20-g18451ed bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1-20-g18451ed bash
```

## 验证

在容器内，确认加速器可见：

```bash
source /opt/hyhal/env.sh && hy-smi
```
