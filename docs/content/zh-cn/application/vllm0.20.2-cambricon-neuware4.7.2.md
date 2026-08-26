---
title: "vllm0.20.2-cambricon-neuware4.7.2"
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
- **宿主机驱动:** 6.5.48

## 镜像内容

### 基于

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.2:2.1.2</code> <a href="../../runtime/cambricon-neuware4.7.2/" title="查看基础镜像详情" aria-label="查看基础镜像详情"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### 应用软件包

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.1+gb954912.d20260826`

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-cambricon-neuware4.7.2:2.1.2-0.2.1_gb954912.d20260826`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-cambricon-neuware4.7.2:2.1.2-0.2.1_gb954912.d20260826
```

### 无需工具包——直接使用 docker / podman

启动交互式 shell：

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG
```

向启动器传参：

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG vllm-serve --model <path> --port 9000
```
