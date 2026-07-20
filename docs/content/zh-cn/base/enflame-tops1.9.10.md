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
title: "enflame-tops1.9.10"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Enflame Zixiao C200 (S60)
- **宿主机驱动:** 1.9.10
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: tencent-container-toolkit >= 2.0.52

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

### SDK 组件

- Enflame driver 1.9.10
- TOPS Runtime 1.9.10
- TOPS CC 1.9.10
- TOPS PTI 1.9.10
- TOPSTX 1.9.10
- TOPS ATen 3.7.20260514
- EFML 1.9.10
- ECCL 3.6.3.11
- Triton GCU 3.6.0+1.0.20260521.cc.1.9.10
- Gculare-perftest 1.9.10

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --network host \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.1 bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/gcu \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.1 bash
```

## 验证

在容器内，确认加速器可见：

```bash
efsmi
```
