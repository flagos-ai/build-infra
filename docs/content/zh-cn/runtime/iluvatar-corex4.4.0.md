---
title: "iluvatar-corex4.4.0"
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
- **芯片型号:** Iluvatar BI-V150
- **宿主机驱动:** 4.4.0
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: ix-container-toolkit >= 1.1.0

## 镜像内容

### 基于

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.2</code> <a href="../../base/iluvatar-corex4.4.0/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### 主要 Python 软件包

- `flag_gems==5.3.4`
- `flagtree==0.6.1+iluvatar3.6`
- `numpy==1.26.4`
- `torch==2.7.1+corex.4.4.0`
- `torchaudio==2.7.1+corex.4.4.0`
- `torchvision==0.22.1+corex.4.4.0`
- <span class="muted"><code class="plain">triton==3.1.0+corex.4.4.0</code></span>

### 切换编译器

本镜像同时包含 FlagTree（默认）和 Triton。在容器内执行 `compiler triton` 可切换到 Triton，执行 `compiler flagtree` 切回，执行 `compiler` 查看当前编译器。

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.1.2 bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.1.2 bash
```

## 验证

在容器内，确认加速器可见：

```bash
ixsmi
```
