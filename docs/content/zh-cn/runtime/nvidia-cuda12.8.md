---
title: "nvidia-cuda12.8"
---

<!--
 Copyright 2026 FlagOS Contributors

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
-->

## 前置条件

- **架构:** x86_64
- **芯片型号:** NVIDIA H20
- **宿主机驱动:** 610.43.02
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: nvidia-container-toolkit

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.1.1`

### Python

3.12

### 主要 Python 软件包

- `flag_gems`
- `flagtree==0.6.0`
- `torch==2.10.0+cu128`
- `torchaudio==2.10.0+cu128`
- `torchvision==0.25.0+cu128`
- <span class="muted"><code class="plain">triton==3.6.0</code></span>

### 切换编译器

本镜像同时包含 FlagTree（默认）和 Triton。在容器内执行 `compiler triton` 可切换到 Triton，执行 `compiler flagtree` 切回，执行 `compiler` 查看当前编译器。

## 环境变量

- `NVIDIA_VISIBLE_DEVICES=all`
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:latest bash
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
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
nvidia-smi
```
