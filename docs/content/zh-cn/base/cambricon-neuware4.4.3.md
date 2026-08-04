---
title: "cambricon-neuware4.4.3"
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
- **芯片型号:** Cambricon MLU590
- **宿主机驱动:** 6.2.15

## 镜像内容

### 基础镜像

`ubuntu:22.04`

### 系统软件包

显式安装；此处版本即为该镜像中实际打包的版本：

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `gdb` — 12.1
- `git` — 2.34.1
- `libc6-dev-i386` — 2.35
- `libncurses5` — 6.3
- `libtinfo5` — 6.3
- `make` — 4.3
- `pciutils` — 3.7.0
- `unzip` — 6.0
- `vim` — 8.2.3995

### SDK 组件

- cnmon 6.2.15
- cntoolkit 4.4.3
- cncl 1.29.4
- cnclep 1.1.1.
- cnnl 2.1.829
- cnnlextra 2.2.7
- mluops 1.8.1

## 环境变量

- `NEUWARE_HOME=/usr/local/neuware`
- `PATH=/usr/local/neuware/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/neuware/lib64`

## 启动

启动交互式 shell（docker 或 podman 均可）：

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.1.1 bash
```

## 验证

在容器内，确认加速器可见：

```bash
cnmon
```
