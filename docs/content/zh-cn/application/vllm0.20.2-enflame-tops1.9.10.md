---
title: "vllm0.20.2-enflame-tops1.9.10"
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
- **芯片型号:** Enflame Zixiao C200 (S60)
- **宿主机驱动:** 1.9.10
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: tencent-container-toolkit >= 2.0.52

## 镜像内容

### 基于

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.9.10:2.1.2</code> <a href="../../runtime/enflame-tops1.9.10/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### 应用软件包

`vllm==0.20.2+flagos`

## 启动

**尚未发布——该镜像还未推送到仓库。下面的 tag 是构建管线届时将推送的版本。**

`harbor.baai.ac.cn/flagos-app/vllm0.20.2-enflame-tops1.9.10:2.1.2`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-enflame-tops1.9.10:2.1.2
```

以下两种方式任选其一：

### 使用容器工具包

启动交互式 shell：

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG
```

向启动器传参：

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG vllm-serve --model <path> --port 9000
```

### 无需工具包——直接使用 docker / podman

启动交互式 shell：

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG
```

向启动器传参：

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG vllm-serve --model <path> --port 9000
```
