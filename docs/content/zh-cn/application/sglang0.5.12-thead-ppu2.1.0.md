---
title: "sglang0.5.12-thead-ppu2.1.0"
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
- **芯片型号:** T-Head PPU-ZW810E
- **宿主机驱动:** 1.3.2-d7f5a2

## 镜像内容

### Python

3.12

### 应用软件包

`sglang==0.5.12+v0.1.0.ppu2.1.0`


`sglang-fl==0.2.0`

### 组件版本

| 组件 | 版本 |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`3bc8649b`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0（backend：`ppu`） |
| torch | 2.10.0 |

## 环境变量

- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_FLAGOS_BLACKLIST=count_nonzero,cumsum`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.12-thead-ppu2.1.0:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.12-thead-ppu2.1.0:2.2.0-0.2.0
```

### 无需工具包——直接使用 docker / podman

启动交互式 shell：

```bash
docker run --rm -it \
  --privileged \
  --shm-size=512g \
  --ipc host \
  --network host \
  -v /dev:/dev \
  $IMG bash
```

以默认设置启动应用：

```bash
docker run --rm -it \
  --privileged \
  --shm-size=512g \
  --ipc host \
  --network host \
  -v /dev:/dev \
  $IMG
```

向启动器传参：

```bash
docker run --rm -it \
  --privileged \
  --shm-size=512g \
  --ipc host \
  --network host \
  -v /dev:/dev \
  $IMG python3 -m sglang.launch_server --model-path <path> --port 30000
```

设备为 PPU SDK 的设备节点（`/dev/alixpu`、`/dev/alixpu_ctl`、`/dev/alixpu_ppu0..15`），`-v /dev:/dev` 会暴露全部节点。只选其中若干张卡时用显式 `--device` 效果相同，例如 `--device /dev/alixpu --device /dev/alixpu_ctl --device /dev/alixpu_ppu0 --device /dev/alixpu_ppu1`。
