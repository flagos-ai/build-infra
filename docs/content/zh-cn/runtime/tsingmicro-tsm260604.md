---
title: "tsingmicro-tsm260604"
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
- **芯片型号:** Tsingmicro TX8110
- **宿主机驱动:** 260604163331.01
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: tx-container-toolkit >= 2.5.0

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260604:2.1.1`

### Python

3.10

### 主要 Python 软件包

- `flag_gems`
- `flagtree==0.5.0.post20260612+git705a4064`
- `torch==2.7.0+cpu`
- `torch_txda==0.1.0+20260615.37ba6bbd`
- `torchaudio==2.7.0+cpu`
- `torchvision==0.22.0+cpu`
- <span class="muted"><code class="plain">triton==3.3.0+gitfe2a28fa</code></span>
- `txops==0.1.0+20260508.60287151`

<p class="muted"><em>灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。</em></p>

## 环境变量

- `USE_TORCH_XLA=0`
- `TORCH_COMPILE_DISABLE=1`

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm260604:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm260604:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
tsm_smi
```
