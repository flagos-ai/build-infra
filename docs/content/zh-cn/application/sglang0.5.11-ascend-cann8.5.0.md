---
title: "sglang0.5.11-ascend-cann8.5.0"
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

- **架构:** aarch64
- **芯片型号:** 昇腾 910C
- **宿主机驱动:** 25.5.0
- **容器工具包:** Ascend-docker-runtime

## 镜像内容

### Python

3.11

### 应用软件包

`sglang==0.5.11`


`sglang-fl==0.2.0`

### 组件版本

| 组件 | 版本 |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.6.0+ascend3.2` |
| FlagCX | `0.13.0` |
| torch | 2.8.0（torch_npu 2.8.0.post2） |
| CANN | 8.5.0 |

## 环境变量

- `ASCEND_RT_VISIBLE_DEVICES` —— 服务使用哪些设备，如 `0,1,2,3`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `HCCL_BUFFSIZE=1000`
- `HCCL_OP_EXPANSION_MODE=AIV`
- `STREAMS_PER_DEVICE=32`
- `SGLANG_ENABLE_OVERLAP_PLAN_STREAM=1`
- `SGLANG_NPU_USE_MULTI_STREAM=1`

启动前必须先 source CANN 与 ATB 的环境：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
```

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-ascend-cann8.5.0:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-ascend-cann8.5.0:2.2.0-0.2.0
```

本镜像未内置默认入口命令，镜像内也**没有** `sglang-serve` 封装——请按下方示例用 `python3 -m sglang.launch_server` 启动服务。

使用容器工具包启动交互式 shell：

```bash
docker run --rm -it \
  --runtime ascend \
  --privileged \
  --network host \
  --shm-size 32g \
  -e ASCEND_VISIBLE_DEVICES=0,1,2,3 \
  -v /path/to/models:/models \
  $IMG bash
```

进入容器后，先 source 环境、导出必需变量，再启动服务：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh

export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export FLAGCX_PATH=/sgl-workspace/FlagCX
export HCCL_BUFFSIZE=1000
export HCCL_OP_EXPANSION_MODE=AIV
export STREAMS_PER_DEVICE=32
export SGLANG_ENABLE_OVERLAP_PLAN_STREAM=1
export SGLANG_NPU_USE_MULTI_STREAM=1

python3 -m sglang.launch_server \
  --model-path /models/Qwen3.6-35B-A3B --tokenizer-path /models/Qwen3.6-35B-A3B \
  --host 0.0.0.0 --port 30000 --tp 4 \
  --attention-backend ascend --device npu --dtype bfloat16 \
  --context-length 32768 --mem-fraction-static 0.8 \
  --cuda-graph-max-bs 60 --disable-radix-cache --trust-remote-code
```

说明：

- `--tp` 要与暴露的设备数一致；选卡在 `docker run` 时用 `ASCEND_VISIBLE_DEVICES`，容器内用 `ASCEND_RT_VISIBLE_DEVICES`。
- 服务需要较大的 `/dev/shm`——启动时务必带 `--shm-size`（不带时容器只有 64 MB，服务会在启动阶段挂住）。
- 该栈上已知编译或运行不通过的 FlagGems 算子黑名单**已内置在镜像里**（`sglang_fl/dispatch/config/ascend.yaml`），自动生效，无需再导出环境变量。
- 若使用带思考链的模型（如 Qwen3 系列），建议加 `--reasoning-parser qwen3`，把思维链拆到 `reasoning_content`。
