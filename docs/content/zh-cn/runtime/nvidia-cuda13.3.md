---
title: "nvidia-cuda13.3"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** NVIDIA H20
- **宿主机驱动:** 610.43.02
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: nvidia-container-toolkit

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.3:2.1.1-30-gd767fb5`

### Python

3.12

### 主要 Python 软件包

- `flag_gems`
- `flagtree==0.6.0`
- `torch==2.11.0+cu130`
- `torchaudio==2.11.0+cu130`
- `torchvision==0.26.0+cu130`
- <span class="muted"><code class="plain">triton==3.6.0</code></span>

<p class="muted"><em>灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。</em></p>

## 环境变量

- `NVIDIA_VISIBLE_DEVICES=all`
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it --gpus all flagos-runtime-nvidia-cuda13.3:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  flagos-runtime-nvidia-cuda13.3:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
nvidia-smi
```
