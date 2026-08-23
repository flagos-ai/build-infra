---
title: "megatron-rl-sunrise-tangrt1.2.0"
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

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-sunrise-tangrt1.2.0:2.1.2</code> <a href="../../runtime/sunrise-tangrt1.2.0/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.10

### 应用软件包

`megatron-core[rl]==0.17.1`

## 启动

**尚未发布——该镜像还未推送到仓库。下面的 tag 是构建管线届时将推送的版本。**

`harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-sunrise-tangrt1.2.0:2.1.2-0.2.1`

启动交互式 shell（docker 或 podman 均可）：

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-sunrise-tangrt1.2.0:2.1.2-0.2.1 bash
```

**暂无启动器。** 该镜像尚未提供启动器或默认命令——可先启动交互式 shell 查看镜像内容；启动器将随应用的入口点一并提供。


## 验证

在容器内，确认加速器可见：

```bash
pt_smi
```
