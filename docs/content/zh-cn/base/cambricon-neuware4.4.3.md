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
title: "cambricon-neuware4.4.3"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Cambricon MLU590
- **宿主机驱动:** 6.2.15

## 镜像内容

### 基础镜像

`ubuntu:24.04`

### 系统软件包

显式安装；此处版本即为该镜像中实际打包的版本：

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `gdb`
- `libc6-dev-i386`
- `libncurses6`
- `libtinfo6`
- `make`
- `pciutils`
- `unzip`

### SDK 组件

- cndev 6.5.25 (amd64)
- cnmon 6.2.15
- cnbin 2.4.2
- cndrv 3.4.3
- cnrt 7.4.0
- cnrtc 0.7.4
- cncc/cnas 5.4.3
- cngdb 4.4.2
- cnpapi 4.4.2
- cnpx 1.6.0
- cnperf 6.4.3
- cnjpeg 0.5.1
- cncodec3 2.4.1
- cnsanitizer 0.12.3
- cnnl+extra 2.1.829
- mluops 1.8.1
- cncl 1.29.4
- cnstudio 1.2.1
- cntoolkit 4.4.3
- cntoolkit-cloud 4.4.3
- cnclep 1.1.1.

## 环境变量

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
