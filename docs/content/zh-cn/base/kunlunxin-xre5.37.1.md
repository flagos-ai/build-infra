---
title: "kunlunxin-xre5.37.1"
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
- **芯片型号:** Kunlunxin P800
- **宿主机驱动:** 5.37.1
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: xpu_container >= 1.0.13

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
- `git` — 2.34.1
- `make` — 4.3
- `pciutils` — 3.7.0
- `unzip` — 6.0
- `vim` — 8.2.3995

### SDK 组件

- CUDA 12.9.0_575.51.03
- XRE-CUDA12 5.37.1.0
- XCUDART 5.13.0

## 环境变量

- `PATH=/usr/local/xpu/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/xpu/lib:/usr/local/xcudart/lib`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.37.1:2.1.2 bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.37.1:2.1.2 bash
```

## 验证

在容器内，确认加速器可见：

```bash
xpu-smi
```

*更新时间: 2026-08-14 21:51:46 · `521f2968843d`*
