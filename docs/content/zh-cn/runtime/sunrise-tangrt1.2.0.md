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

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-sunrise-tangrt1.2.0:2.1.1`

### Python

3.10

### 主要 Python 软件包

- `flag_gems`
- `torch-ptpu==0.2.3+torch2.11`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- `triton==3.4.0.6+gite4f6d6e4`

## 启动

在容器中启动交互式 shell：

```bash
docker run --rm -it \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-sunrise-tangrt1.2.0:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
pt_smi
```
