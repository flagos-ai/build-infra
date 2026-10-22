---
title: vllm-plugin-FL
weight: 10
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


vllm-plugin-FL 以预构建 wheel 的形式从厂商 PyPI 安装进每个 vLLM app 镜像。
多数后端使用纯 Python wheel；少数后端使用**原生** wheel——额外携带编译好的
`vllm_fl._C` 扩展。

## 原生扩展是做什么的

`vllm_fl._C` 提供插件的 `weak_ref_tensor` 算子。vLLM cudagraph 捕获需要对
被捕获张量的真正弱引用；扩展缺失时，插件回退到一个持有**强**引用的恒等
实现，每个被捕获的图都会泄漏显存，直至捕获阶段 OOM。

## 哪些后端用原生 wheel

该扩展注册在 CUDA 上，因此只对 torch 确实走 CUDA 键调度的后端有意义。共
六个后端：

- `nvidia-cuda12.8`、`nvidia-cuda13.3`
- `metax-maca3.7.2.1`、`metax-maca3.8.1.3`
- `hygon-dtk26.04`
- `kunlunxin-xre5.37.1`

其余后端（ascend、cambricon、enflame、mthreads、sunrise、tsingmicro、iluvatar
等）一律使用纯 Python wheel。

## 为什么没有 builder 镜像

与 FlagTree 或 FlagCX 不同，原生 wheel 没有自己的 Containerfile。它在**每个
后端的运行时镜像内**构建（`flagos-runtime-<vendor>-<backend>`），因为编译出的
扩展必须链接 app 镜像实际运行时的那套 torch/ABI/glibc——构建环境必须等于
交付环境。单独的 toolchain 镜像可能与实际交付物产生偏差。

## Wheel 标签

原生 wheel 的本地版本标签等于裸后端名（`-` 折叠为 `.`）：

| 后端 | Wheel |
|---|---|
| `nvidia-cuda12.8` | `0.3.0+cuda12.8` |
| `nvidia-cuda13.3` | `0.3.0+cuda13.3` |
| `metax-maca3.7.2.1` | `0.3.0+maca3.7.2.1` |
| `metax-maca3.8.1.3` | `0.3.0+maca3.8.1.3` |
| `hygon-dtk26.04` | `0.3.0+dtk26.4` |
| `kunlunxin-xre5.37.1` | `0.3.0+xre5.37.1` |

没有 vendor 前缀——wheel 已经落到 per-vendor 的索引上（`flagos-pypi-<vendor>`），
加上 vendor 就重复了。app 构建从后端名推导完整 pin，因此一次派发只需给出
公共版本号（`0.3.0`）。

## 完整理由

设计记录在代码旁：

- [packaging/vllm/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/vllm/DESIGN.md) —— 面向维护者的决策记录。
- [packaging/vllm/plugin-build.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/vllm/plugin-build.yaml) —— 每个后端的构建开关及其理由。
