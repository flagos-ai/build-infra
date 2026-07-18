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

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.1-31-g853fdf7`

### Python

3.12

### 主要 Python 软件包

- `flag_gems`
- `flagtree==0.6.0+enflame3.6`
- `flash-attn==2.7.2+torch.2.9.1.gcu.3.4.20260323`
- `pyefml==1.9.10`
- `torch-gcu==2.10.0+3.7.20260408`
- `torch==2.10.0+cpu`
- `torchaudio==2.10.0+cpu`
- `torchvision==0.25.0+cpu`
- <span class="muted"><code class="plain">triton-gcu==3.6.0+1.0.20260521.cc.1.9.10</code></span>

<p class="muted"><em>灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。</em></p>

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --network host \
  -e TENCENT_VISIBLE_DEVICES=all \
  flagos-runtime-enflame-tops1.9.10:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it --device /dev/gcu flagos-runtime-enflame-tops1.9.10:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
efsmi
```
