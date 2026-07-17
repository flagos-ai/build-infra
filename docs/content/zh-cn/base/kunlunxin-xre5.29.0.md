---
title: "kunlunxin-xre5.29.0"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Kunlunxin P800
- **宿主机驱动:** 5.29.0.0
- **容器工具包** <abbr title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">*(可选)*</abbr>: xpu_container >= 1.0.13

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
- `kmod`
- `pciutils`

### SDK 组件

- CUDA 12.9.0_575.51.03
- XRE-CUDA12 5.29.0.0
- XCUDART 5.13.0

## 环境变量

- `PATH=/usr/local/xpu/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/xpu/lib:/usr/local/xcudart/lib`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1-20-g9ab46c9 bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1-20-g9ab46c9 bash
```

## 验证

在容器内，确认加速器可见：

```bash
xpu-smi
```
