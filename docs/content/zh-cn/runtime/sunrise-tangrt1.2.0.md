---
title: "sunrise-tangrt1.2.0"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Sunrise SR-SUN-S2-X1
- **宿主机驱动:** 0.24.0

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1-30-gd767fb5`

### Python

3.10

### 主要 Python 软件包

- `flag_gems`
- `torch-ptpu==0.2.3+torch2.11`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- `triton==3.4.0.6+gite4f6d6e4`

## 启动

在容器中启动交互式 shell：

```bash
docker run --rm -it flagos-runtime-sunrise-tangrt1.2.0:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
pt_smi
```
