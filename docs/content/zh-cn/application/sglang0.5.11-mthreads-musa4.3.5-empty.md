---
title: "sglang0.5.11-mthreads-musa4.3.5-empty"
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
- **芯片型号:** MTT S5000
- **宿主机驱动:** 3.3.5-server（`musa` 驱动包）
- **容器工具包:** MUSA 4.3.5（镜像自带）

## 镜像内容

### Python

3.10

### 应用包

`sglang==0.5.11`


`sglang-fl==0.2.0`

### 组件版本

| 组件 | 版本 |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`4819c19`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0（后端：`mthreads`） |
| torch | 2.9.0（torch_musa 2.9.0） |

> 这是**设备解耦（empty）**形态：算子全部由 FlagGems/FlagTree 提供，不走厂商原生 kernel。

## 环境变量

- `source /root/.virtualenvs/sglang-0.5.6/bin/activate` —— **必做**。sglang 与各 FlagOS 组件装在该虚拟环境里；不激活时 `python3` 会落到基础镜像里较旧的 `flag_gems` / `sglang_fl`。
- `MUSA_VISIBLE_DEVICES` —— 选卡，例如 `0,1,2,3`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_MUSA_FP32_TP_ALLREDUCE=1`
- `SGLANG_FL_PER_OP="silu_and_mul=flagos;mrotary_embedding=flagos;topk=reference;gemma_rms_norm=reference;fused_moe=vendor;chunk_gated_delta_rule=vendor;fused_recurrent_gated_delta_rule=vendor"` —— 设备解耦模式的逐算子路由表
- `MCCL_SOCKET_IFNAME=bond0`、`GLOO_SOCKET_IFNAME=bond0` —— 多卡通信网卡
- `MCCL_TIMEOUT=14400`
- `TORCH_COMPILE_DISABLE=1` —— FlagTree 的 `mthreads` triton spec 会遮蔽标准 triton，`torch.compile` 会在 import 阶段报错

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-mthreads-musa4.3.5-empty:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-mthreads-musa4.3.5-empty:2.2.0-0.2.0
```

### 无需工具包——直接使用 docker / podman

本镜像未内置默认入口命令，请显式给出启动命令。

启动交互式 shell（MUSA 设备访问需要 `--privileged`）：

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  --shm-size 512g \
  -e MTHREADS_VISIBLE_DEVICES=all \
  -v <模型目录>:/models \
  $IMG bash
```

进入容器后，以 `tp=4` 启动服务：

```bash
source /root/.virtualenvs/sglang-0.5.6/bin/activate
export MUSA_VISIBLE_DEVICES=0,1,2,3
export FLAGCX_PATH=/sgl-workspace/FlagCX
export SGLANG_FL_DIST_BACKEND=flagcx
export SGLANG_MUSA_FP32_TP_ALLREDUCE=1
export SGLANG_FL_PER_OP="silu_and_mul=flagos;mrotary_embedding=flagos;topk=reference;gemma_rms_norm=reference;fused_moe=vendor;chunk_gated_delta_rule=vendor;fused_recurrent_gated_delta_rule=vendor"
export MCCL_SOCKET_IFNAME=bond0
export GLOO_SOCKET_IFNAME=bond0
export MCCL_TIMEOUT=14400
export TORCH_COMPILE_DISABLE=1
python3 -m sglang.launch_server --model-path /models/<模型> --host 0.0.0.0 --port 30000 \
  --tp-size 4 --page-size 64 --disable-piecewise-cuda-graph --disable-radix-cache \
  --trust-remote-code --mem-fraction-static 0.75 --reasoning-parser qwen3 --cuda-graph-max-bs 32
```

> 若模型是 thinking 模型（如 Qwen3 系列），`--reasoning-parser qwen3` 必加，否则思维链不会分离到 `reasoning_content`。
