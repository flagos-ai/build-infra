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

### 基础镜像

`ubuntu:24.04`

### 系统软件包

显式安装；此处版本即为该镜像中实际打包的版本：

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `pciutils` — 3.10.0
- `vim` — 9.1.0016

### SDK 组件

- Tang Toolkit 1.2.0
- PCCL 1.2.0
- taDNN 1.2.0
- taBLAS 1.2.0

## 环境变量

- `TANGRT_ROOT=/usr/local/tangrt`
- `LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`
- `LD_LIBRARY_PATH=/usr/local/tangrt/targets/linux-x86_64/lib:/usr/local/tangrt/lib/linux-x86_64`

## 启动

启动交互式 shell（docker 或 podman 均可）：

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1 bash
```

## 验证

在容器内，确认加速器可见：

```bash
pt_smi
```
