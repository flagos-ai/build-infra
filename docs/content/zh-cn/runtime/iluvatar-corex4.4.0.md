---
title: "iluvatar-corex4.4.0"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Iluvatar BI-V150
- **宿主机驱动:** 4.4.0
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: ix-container-toolkit >= 1.1.0

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1-30-gd767fb5`

### Python

3.10

### 主要 Python 软件包

- `flag_gems`
- `torch==2.7.1+corex.4.4.0`
- `torchaudio==2.7.1+corex.4.4.0`
- `torchvision==0.22.1+corex.4.4.0`
- `triton==3.1.0+corex.4.4.0`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  flagos-runtime-iluvatar-corex4.4.0:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  flagos-runtime-iluvatar-corex4.4.0:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
ixsmi
```
