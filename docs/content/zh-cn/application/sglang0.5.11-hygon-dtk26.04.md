---
title: "sglang0.5.11-hygon-dtk26.04"
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
- **芯片型号:** Hygon BW1000
- **宿主机驱动:** 6.3.30-V1.4.1a

## 镜像内容

### Python

3.10

### 应用软件包

`sglang==0.5.11`


`sglang-fl==0.2.0`

### 组件版本

| 组件 | 版本 |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`3bc8649b`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0 (backend: `hcu`) |
| torch | 2.10.0 |

## 环境变量

- `LD_LIBRARY_PATH` 需追加 `/usr/local/lib/python3.10/dist-packages/torch/lib:/opt/dtk/cuda/cuda-12/lib64`，否则 FlagCX 加载时报 `libcudart.so.12: cannot open shared object file`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_FLAGOS_BLACKLIST=cumsum,layer_norm`
- `SGLANG_FL_PREFER=vendor`
- `SGLANG_FL_STRICT=1`

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-hygon-dtk26.04:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-hygon-dtk26.04:2.2.0-0.2.0
```

### 无需工具包——直接使用 docker / podman

本镜像未内置默认入口命令，请显式给出启动命令。

启动交互式 shell：

```bash
docker run --rm -it \
  --network host \
  --ipc host \
  --privileged \
  --group-add video \
  --cap-add SYS_PTRACE \
  --security-opt seccomp=unconfined \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  -v /opt/hyhal:/opt/hyhal:ro \
  -e HIP_VISIBLE_DEVICES=0,1 \
  -e CUDA_VISIBLE_DEVICES=0,1 \
  $IMG bash
```

⚠️ 选卡必须通过 `docker run -e` 固化（上面的 `HIP_VISIBLE_DEVICES` / `CUDA_VISIBLE_DEVICES`）；进入容器后再临时 `export` 会导致设备枚举卡死。

进入容器后，以 `tp=2` 启动服务：

```bash
source /opt/dtk/env.sh
export LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/torch/lib:/opt/dtk/cuda/cuda-12/lib64:$LD_LIBRARY_PATH
export FLAGCX_PATH=/sgl-workspace/FlagCX
export SGLANG_FL_DIST_BACKEND=flagcx
export SGLANG_FL_FLAGOS_BLACKLIST=cumsum,layer_norm
export SGLANG_FL_PREFER=vendor
export SGLANG_FL_STRICT=1
python3 -m sglang.launch_server --model-path <path> --host 0.0.0.0 --port 30000 --tp 2 --page-size 64 --disable-radix-cache --context-length 262144 --mem-fraction-static 0.80 --chunked-prefill-size 4096 --max-running-requests 64 --trust-remote-code --disable-piecewise-cuda-graph --reasoning-parser qwen3
```

> 若模型是 thinking 模型（如 Qwen3 系列），`--reasoning-parser qwen3` 必加，否则思维链不会分离到 `reasoning_content`。
