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
title: "kunlunxin-xre5.29.0"
---

## 前置条件

- **架构:** x86_64
- **芯片型号:** Kunlunxin P800
- **宿主机驱动:** 5.29.0.0
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: xpu_container >= 1.0.13

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.29.0:2.1.1-31-g853fdf7`

### Python

3.10

### 主要 Python 软件包

- `apex==0.1`
- `benchflow==1.0.0`
- `colorama==0.4.6`
- `flag_gems`
- `flagtree==0.5.1+xpu3.0`
- `flash_attn==2.4.2+7e2dd4d`
- `hydrax==0.1.0`
- `hyperparameter==0.5.6`
- `psutil==6.1.0`
- `regex==2026.4.4`
- `torch==2.9.0+cu129`
- `torch_plugin==0.1.0`
- `torch_xray==2.0.4`
- `torchaudio==2.9.0+cu129`
- `torchvision==0.24.0+cu129`
- <span class="muted"><code class="plain">triton==3.0.0+a48aedef</code></span>
- `xformers==0.0.29+1e7a8ec.d20260114`
- `xmlir==1.0.0.1`

<p class="muted"><em>灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。</em></p>

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  flagos-runtime-kunlunxin-xre5.29.0:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  flagos-runtime-kunlunxin-xre5.29.0:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
xpu-smi
```
