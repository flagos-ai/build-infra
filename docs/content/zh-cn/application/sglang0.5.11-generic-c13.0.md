---
title: "sglang0.5.11-generic-c13.0"
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
- **芯片型号:** H800
- **宿主机驱动:** 580.159.03

## 镜像内容

### Python

3.12

### 应用软件包

`sglang==0.5.11`


`sglang-fl==0.2.0`

### 组件版本

| 组件 | 版本 |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 |
| torch | 2.11.0 |

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-generic-c13.0:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-generic-c13.0:2.2.0-0.2.0
```

### 直接使用 docker / podman

启动交互式 shell：

```bash
docker run --rm -it \
  --gpus all \
  --ipc host \
  --shm-size=512g \
  -v /path/to/models:/models \
  $IMG bash
```

向启动器传参：

```bash
docker run --rm -it \
  --gpus all \
  --ipc host \
  --shm-size=512g \
  -v /path/to/models:/models \
  $IMG python3 -m sglang.launch_server --model-path /models/Qwen3.6-35B-A3B --tp 4 --host 0.0.0.0 --port 30000 --trust-remote-code
```

该镜像不含默认启动器，也没有 `sglang-serve` 封装命令——按上面的方式用 `python3 -m sglang.launch_server` 起服务。要限定容器可见的设备，用 `--gpus` 并在设备列表外加引号，例如 `--gpus '"device=4,5,6,7"'`。
