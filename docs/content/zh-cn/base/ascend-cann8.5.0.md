---
title: "ascend-cann8.5.0"
---

## 前置条件

- **架构:** aarch64
- **芯片型号:** Ascend 910B
- **宿主机驱动:** 25.5.0
- **容器工具包** <abbr title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">*(可选)*</abbr>: Ascend-docker-runtime >= 6.0.RC3

## 镜像内容

### 基础镜像

`ubuntu:24.04`

### 系统软件包

显式安装；此处版本即为该镜像中实际打包的版本：

- `ca-certificates`
- `software-properties-common`

### SDK 组件

- CANN Toolkit 8.5.0 (aarch64)
- CANN 910B Ops 8.5.0 (aarch64)

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1-20-g9ab46c9 bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1-20-g9ab46c9 bash
```

## 验证

在容器内，确认加速器可见：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh && npu-smi info
```
