---
title: "cambricon-neuware4.4.3"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Cambricon MLU590
- **宿主机驱动:** 6.2.15

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.1.1-30-gd767fb5`

### Python

3.10

### 主要 Python 软件包

- `cambricon_dali==0.13.0`
- `flag_gems`
- `torch-mlu-ops==1.8.0+torch2.7.1`
- `torch-mlu==1.29.2+torch2.7.1`
- `torch==2.7.1+cpu`
- `triton==3.2.0+mlu1.7.2`

## 启动

启动交互式 shell（docker 或 podman 均可）：

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  flagos-runtime-cambricon-neuware4.4.3:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
cnmon
```
