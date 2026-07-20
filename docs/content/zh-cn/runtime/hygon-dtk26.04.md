---
title: "hygon-dtk26.04"
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
- **芯片型号:** Hygon BW1000
- **宿主机驱动:** 6.3.30-V1.4.1a
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: dcu-container-toolkit >= 1.3.0

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1`

### Python

3.10

### 主要 Python 软件包

- `flag_gems`
- `flagtree==0.5.1+hcu3.1`
- `torch==2.9.0+das.opt1.dtk2604`
- <span class="muted"><code class="plain">triton==3.3.0+das.opt1.dtk2604.torch290</code></span>

<p class="muted"><em>灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。</em></p>

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
source /opt/hyhal/env.sh && hy-smi
```
