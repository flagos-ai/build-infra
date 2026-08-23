---
title: "megatron-training-nvidia-cuda13.3"
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

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:2.1.2</code> <a href="../../runtime/nvidia-cuda13.3/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### 应用软件包

`megatron-core[training]==0.17.1`

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f`

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f
```

向启动器传参：

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f megatron-train --model-type GPT
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
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f
```

向启动器传参：

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f megatron-train --model-type GPT
```

## 验证

在容器内，确认加速器可见：

```bash
nvidia-smi
```
