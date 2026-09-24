---
title: "sglang0.5.11-enflame-tops1.10.6"
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
- **芯片型号:** Enflame Zixiao C200 (S60)
- **宿主机驱动:** 1.9.10

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
| FlagTree | `0.7.0+triton3.6` (`3bc8649b`) |
| FlagCX | `0.13.0` |
| triton | 3.6.0（backend：`enflame`） |
| torch | 2.11.0（torch_gcu 2.11.0） |

## 环境变量

- `TORCH_GCU_ENABLE_INT64_AND_UINT64=1`
- `ENABLE_I64_CHECK=0`
- `TORCHDYNAMO_DISABLE=1`
- `SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_IDLE=0`
- `FLAGCX_PATH=/sgl-workspace/FlagCX`
- `SGLANG_FL_DIST_BACKEND=flagcx`
- `SGLANG_FL_FLAGOS_BLACKLIST=isin,_unique2`

## 启动

**已发布:** `harbor.baai.ac.cn/flagos-app/sglang0.5.11-enflame-tops1.10.6:2.2.0-0.2.0`

镜像名较长——先将其设为变量：

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.11-enflame-tops1.10.6:2.2.0-0.2.0
```

### 无需工具包——直接使用 docker / podman

启动交互式 shell：

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  -v /path/to/models:/models \
  $IMG bash
```

向启动器传参：

```bash
docker run --rm -it \
  --privileged \
  --ipc host \
  --network host \
  -v /path/to/models:/models \
  -e TOPS_VISIBLE_DEVICES=4,5,6,7 \
  -e TORCH_GCU_ENABLE_INT64_AND_UINT64=1 \
  -e ENABLE_I64_CHECK=0 \
  -e TORCHDYNAMO_DISABLE=1 \
  -e SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_IDLE=0 \
  -e FLAGCX_PATH=/sgl-workspace/FlagCX \
  -e SGLANG_FL_DIST_BACKEND=flagcx \
  -e SGLANG_FL_FLAGOS_BLACKLIST=isin,_unique2 \
  $IMG bash -c "python3 -m sglang.launch_server --model-path /models/Qwen3.6-27B --tp 4 --host 0.0.0.0 --port 30000 --trust-remote-code --mem-fraction-static 0.6 --disable-piecewise-cuda-graph --reasoning-parser qwen3 --attention-backend fa3"
```

镜像内**没有** `sglang-serve` 封装命令——按上面的方式用 `python3 -m sglang.launch_server` 启动。
限制容器可见的设备时，把 `TOPS_VISIBLE_DEVICES` 设为逗号分隔的卡号（如上）；不设置则使用全部 GCU 设备。

**关于上面这条命令**

- ⚠️ **启动参数必须用 `bash -c "..."` 包起来。** 镜像的 `ENTRYPOINT` 是厂商的包装脚本（`dev_entrypoint`），
  最后一步是 `bash -c "$@"` —— 参数多于一个时，**只有第一个词被当作命令**，其余会被静默丢弃；
  所以写成 `$IMG python3 -m sglang.launch_server --tp 4 ...` 实际只跑了一个不带参数的空 `python3`，容器随即退出。
  在已发布镜像上实测：`$IMG echo HELLO` 无输出，`$IMG bash -c "echo HELLO"` 正常。
- Zixiao C200（S60）上 `--mem-fraction-static 0.6` 是必须的：每张 GCU 实际可用仅约 40.9 GiB，`--tp 4` 跑 27B 时用 `0.7` 会 OOM。
- 新容器**首次启动较慢**——FlagTree 的 `enflame` 后端在首次用到 kernel 时才编译。大约 4 分钟 graph capture，再加数分钟 warmup，之后才会打印 `The server is fired up and ready to roll!`。这段时间是 CPU 编译，不是卡死。
- `SGLANG_FL_FLAGOS_BLACKLIST=isin,_unique2` 让 `torch.isin` 与 `torch.unique` 回退到厂商实现。这是该工具链下**厂商文档给定的配置**，与本版本发布无关。

