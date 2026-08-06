---
title: "sunrise-tangrt1.2.0"
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
- **芯片型号:** Sunrise SR-SUN-S2-X1
- **宿主机驱动:** 0.24.0

## 镜像内容

### 基于

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.2</code> <a href="../../base/sunrise-tangrt1.2.0/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.10

### 主要 Python 软件包

- `flag_gems==5.3.2`
- `flagtree==0.6.0+sunrise3.6`
- `numpy==2.2.6`
- `torch-ptpu==0.2.3+torch2.11`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- <span class="muted"><code class="plain">triton==3.6.0.1+git0a5cfb35</code></span>

### 切换编译器

本镜像同时包含 FlagTree（默认）和 Triton。在容器内执行 `compiler triton` 可切换到 Triton，执行 `compiler flagtree` 切回，执行 `compiler` 查看当前编译器。

## 启动

启动交互式 shell（docker 或 podman 均可）：

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-sunrise-tangrt1.2.0:2.1.2 bash
```

## 验证

在容器内，确认加速器可见：

```bash
pt_smi
```
