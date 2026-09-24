---
title: "sglang0.5.12-kunlunxin-xre5.37.1"
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
- **芯片型号:** KunlunXin P800 OAM（96 GiB / 卡）
- **宿主机驱动:** 5.37.1.0

## 镜像内容

### Python

3.10.12

### 应用软件包

`sglang==0.5.12`

`sglang-fl==0.2.0`

### 组件版本

| 组件 | 版本 |
| --- | --- |
| FlagGems | `5.4.0` (`6ed2f390`) |
| FlagTree | `0.7.0+triton3.6` (`4819c190`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0（backend：`xpu`） |
| torch | 2.9.0（torch_xmlir `XMLIR-v2.9.0`，XRE 5.35.0.0 / XCCL 3.1.9.0） |

## 环境变量

- `SGLANG_FL_CONFIG=/sgl-workspace/sglang-plugin-FL/sglang_fl/dispatch/config/kunlunxin.yaml`（**必需**，见下）
- `XPU_VISIBLE_DEVICES=0,1,2,3`（与 `CUDA_VISIBLE_DEVICES` 同值，两个都设）
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `USE_FLAGGEMS=1`
- `USE_FLAGTUNE=0`
- `MM_ATTENTION_BACKEND=sdpa`

> ⚠️ **`SGLANG_FL_CONFIG` 是必需项，不是可选项。** 插件不设该变量时会去自动探测平台，
> 而在本栈下探测结果是 `nvidia`（`torch.cuda.is_available()` 为真），于是加载到空配置
> `config/nvidia.yaml`，**镜像内置的 43 条算子黑名单一条都不会生效，服务起不来**。
>
> ⚠️ 该黑名单本身也是这个镜像跑得起来的前提：昆仑芯 XPU 编译器在本版仍有两处未修缺陷
> （`tl.exp2` 被降级、compare-fusion 下 `cmpf` 类型错），黑名单把这些算子退回原生实现绕过。

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.12-kunlunxin-xre5.37.1:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.12-kunlunxin-xre5.37.1:2.2.0-0.2.0
```

### 无需工具包——直接使用 docker / podman

启动交互式 shell：

```bash
docker run --rm -it \
  --privileged \
  --network host \
  --shm-size=512g \
  -v /public-flash/models:/models \
  $IMG bash
```

向启动器传参：

```bash
docker run --rm -it \
  --privileged \
  --network host \
  --shm-size=512g \
  -v /public-flash/models:/models \
  -e SGLANG_FL_CONFIG=/sgl-workspace/sglang-plugin-FL/sglang_fl/dispatch/config/kunlunxin.yaml \
  -e FLAGCX_PATH=/sgl-workspace/FlagCX \
  -e USE_FLAGGEMS=1 \
  -e USE_FLAGTUNE=0 \
  -e MM_ATTENTION_BACKEND=sdpa \
  $IMG python3 -m sglang.launch_server --model-path <path> --tp-size 4 --host 0.0.0.0 --port 30000 --page-size 1 --mem-fraction-static 0.75 --watchdog-timeout 3600 --attention-backend kunlunxin --disable-piecewise-cuda-graph --cuda-graph-max-bs 60 --sampling-backend pytorch --mm-attention-backend sdpa --reasoning-parser qwen3 --trust-remote-code
```

> ⚠️ 上面 `-e SGLANG_FL_CONFIG=…` **不能省**（原因见「环境变量」一节）；交互式 shell 那种用法要在容器内自行 `export`。

设备为昆仑芯 XPU 设备节点，`--privileged` 会暴露全部节点。选卡用 `XPU_VISIBLE_DEVICES` 与
`CUDA_VISIBLE_DEVICES` **同时**指定（两个都设，同样用 `-e` 传），例如
`-e XPU_VISIBLE_DEVICES=4,5,6,7 -e CUDA_VISIBLE_DEVICES=4,5,6,7`。
