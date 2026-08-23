---
title: "vllm-metax-maca3.7.2.1"
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
- **芯片型号:** MetaX C550
- **宿主机驱动:** 3.8.30
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: metax-docker >= 0.15.3

## 镜像内容

### 基于

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.7.2.1:2.1.2</code> <a href="../../runtime/metax-maca3.7.2.1/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### 应用软件包

`vllm==0.24.0+flagos`

## 启动

**尚未发布——该镜像还未推送到仓库。下面的 tag 是构建管线届时将推送的版本。**

`harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2`

**使用容器工具包** *(可选)*：

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 bash
```

以默认设置启动应用：

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2
```

向启动器传参：

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 vllm-serve --model <path> --port 9000
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2
```

向启动器传参：

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 vllm-serve --model <path> --port 9000
```

## 验证

在容器内，确认加速器可见：

```bash
mx-smi
```
