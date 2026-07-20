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
---
title: "mthreads-musa5.2.0"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** MThreads MTT S5000
- **宿主机驱动:** 5.2.0-server
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa5.2.0:2.1.1`

### Python

3.10

### 主要 Python 软件包

- `flag_gems`
- `flagtree==0.6.0+mthreads3.6`
- `mkl==2024.0.0`
- `torch==2.9.0+musa5.2.0`
- `torch_musa==2.9.1`
- <span class="muted"><code class="plain">triton==3.6.0</code></span>

<p class="muted"><em>灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。</em></p>

## 环境变量

- `MTHREADS_VISIBLE_DEVICES=all`
- `LD_LIBRARY_PATH=${VIRTUAL_ENV}/lib:${LD_LIBRARY_PATH}`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa5.2.0:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
mthreads-gmi
```
