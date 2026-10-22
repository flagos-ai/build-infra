---
title: Megatron
weight: 60
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


Megatron app 镜像 = runtime 镜像 + 从
[Megatron-LM-FL](https://github.com/flagos-ai/Megatron-LM-FL) fork 构建的
megatron-core wheel 的**单步 `pip install`**。与 vLLM/SGLang 不同——那两者
repack sdist 以剥离 torch 依赖——megatron 走的是 **fork 源码**路径：wheel 保留
`torch>=2.6.0` 声明，runtime 的 vendor torch 满足它，于是 pip 什么都不解析、
无需任何依赖手术。

## 为什么 wheel 是 CPython-ABI 特定的

megatron-core 带编译扩展（`helpers_cpp`，pybind11），所以每个 wheel 都是
`cp310` / `cp311` / `cp312`——从不是 `py3-none-any`——而且三者都得构建，因为
runtime 矩阵三种 Python 都在用。该扩展在上游声明为 `optional=True` 却被
无条件 import，所以构建以「`.so` 必须在 wheel 内」为门禁，而不是信任编译。

## 构建环境 = 后端 runtime 镜像本身

wheel **在后端自己的 runtime 镜像内**构建，而非单独的 builder 镜像：runtime
带着它将要运行的确切 Python、torch 与 `pybind11==3.0.3`，于是 ABI 契约按构造
匹配，安装也在它实际交付的那个镜像里被证明是惰性的。

## 一次安装，无 `--no-deps`

app 安装是 `pip install "megatron-core[training|rl]==<version>"`——extra 选择
场景（`[training]` = modelopt/tqdm/datasets，`[rl]` = GRPO）。pin 带本地标签
（`+fl.<date>.g<sha>`），因为裸 `0.17.1` 会匹配该版本的所有 fork 构建，pip 会
取索引上最高的那个。同一个安装还带 `scipy<1.18` 守卫，防止 modelopt 把
numpy 2.0 拖到 runtime 的 numpy 1.26 pin 之上。

## RL 已暂停

megatron_rl 已暂停（2026-08-31）：RL 线转向 verl，Megatron RL 矩阵列标 ⏸。
这里只有 training app 处于活跃。

## 完整理由

设计记录就在代码旁：

- [packaging/megatron/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/megatron/DESIGN.md) —— 决策，面向维护者。
- [packaging/megatron/builder/README.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/megatron/builder/README.md) —— 如何运行 wheel 构建。
- [packaging/megatron/docs/megatron-0.17.1/decisions.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/megatron/docs/megatron-0.17.1/decisions.md) —— ADR 记录（fork vs repack、helpers_cpp、no-deps、版本格式）。
