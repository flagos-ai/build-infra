---
title: "sglang0.5.11-iluvatar-corex4.5.0"
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
- **芯片型号:** Iluvatar BI-V150
- **宿主机驱动:** 4.5.0

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
| FlagTree | `0.7.0+triton3.6` (`4819c190`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `iluvatar`) |
| torch | 2.10.0 |

## 环境变量

- `LD_LIBRARY_PATH` 需前置 `/usr/local/corex-host/lib64`，并保留末尾的 `:$LD_LIBRARY_PATH`。不加时 `torch.cuda.is_available()` 会静默返回 `False`，而 `device_count()` 仍报 16——原因是镜像自带的 corex 运行时与宿主机驱动不匹配。
- `CUDA_VISIBLE_DEVICES` — 选卡
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_PREFER=vendor`
- `SGLANG_FL_FLAGOS_BLACKLIST=max`
- `ATTENTION_BACKEND=triton`
- `NCCL_IB_DISABLE=1`
- `USE_FLAGTUNE=0` — FlagTune 不支持 `corex` 后端，不关会启动中止

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-iluvatar-corex4.5.0:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-iluvatar-corex4.5.0:2.2.0-0.2.0
```

### 无需工具包——直接使用 docker / podman

本镜像未内置默认的应用入口命令，请显式给出启动命令。

启动交互式 shell：

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  --pid host \
  -v /dev:/dev \
  -v /lib/modules:/lib/modules \
  -v /sys:/sys \
  -v /usr/local/corex-4.5.0.20260509:/usr/local/corex-host \
  -v /path/to/models:/models \
  $IMG bash
```

向启动器传参：

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  --pid host \
  -v /dev:/dev \
  -v /lib/modules:/lib/modules \
  -v /sys:/sys \
  -v /usr/local/corex-4.5.0.20260509:/usr/local/corex-host \
  -v /path/to/models:/models \
  -e LD_LIBRARY_PATH=/usr/local/corex-host/lib64 \
  -e CUDA_VISIBLE_DEVICES=0,1,2,3 \
  $IMG python3 -m sglang.launch_server --model-path /models/Qwen3.6-27B --tp-size 4 --host 0.0.0.0 --port 30000
```

涉及的设备为 `/dev/iluvatar0` … `/dev/iluvatar15` 以及 `/dev/itrctl`、`/dev/itrlink`；`-v /dev:/dev` 会把它们全部暴露出来。要只暴露一部分，用显式 `--device` 即可，例如 `--device /dev/iluvatar0 --device /dev/iluvatar1 --device /dev/itrctl`。

> **必须**把**宿主机**的 corex 目录挂进去（`/usr/local/corex-4.5.0.20260509` → `/usr/local/corex-host`）：镜像自带的 corex 运行时与宿主机驱动不匹配，不挂的话 CUDA 初始化会静默失败，表现为「能看到卡但用不了」。路径要与宿主机上实际安装的 corex 版本一致。

> 若模型是 thinking 模型（如 Qwen3 系列），需加 `--reasoning-parser qwen3`，否则思维链不会分离到 `reasoning_content`。
