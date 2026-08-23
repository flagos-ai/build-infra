---
title: "megatron-training-hygon-dtk26.04"
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

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2</code> <a href="../../runtime/hygon-dtk26.04/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.10

### 应用软件包

`megatron-core[training]==0.17.1`

## 启动

**尚未发布——该镜像还未推送到仓库。下面的 tag 是构建管线届时将推送的版本。**

`harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-hygon-dtk26.04:2.1.2-0.2.1`

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-hygon-dtk26.04:2.1.2-0.2.1 bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-hygon-dtk26.04:2.1.2-0.2.1
```

向启动器传参：

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-hygon-dtk26.04:2.1.2-0.2.1 megatron-train --model-type GPT
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
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-hygon-dtk26.04:2.1.2-0.2.1 bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-hygon-dtk26.04:2.1.2-0.2.1
```

向启动器传参：

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-hygon-dtk26.04:2.1.2-0.2.1 megatron-train --model-type GPT
```

## 验证

在容器内，确认加速器可见：

```bash
hy-smi
```
