---
title: "sunrise-tangrt1.2.0"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Sunrise SR-SUN-S2-X1
- **宿主机驱动:** 0.24.0

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

- Tang Toolkit 1.2.0
- PCCL 1.2.0
- taDNN 1.2.0
- taBLAS 1.2.0

## 环境变量

- `TANGRT_ROOT=/usr/local/tangrt`
- `LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`
- `LD_LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`

## 启动

在容器中启动交互式 shell：

```bash
docker run --rm -it \
  harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1-21-g7fe5cbd bash
```

## 验证

在容器内，确认加速器可见：

```bash
pt_smi
```
