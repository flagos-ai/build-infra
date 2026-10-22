---
title: SGLang
weight: 70
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


SGLang app 镜像 = runtime 镜像 + 从自建 sdist repack 出的 per-vendor wheel 的
**单步 `pip install`**。原生 wheel 会顶掉 runtime 的 torch 矩阵，所以本线从
**非 CUDA（`srt_empty`）变体**构建：其 METADATA 按构造零 torch、零
`sgl-kernel`，repack 只需打上 `+flagos` 版本后缀。

## 为什么 repack 而非 fork

与 Megatron 不同——它从 fork 构建 wheel，fork 的 torch 声明由 runtime 满足
——sglang 没有这么干净的基座：其 CUDA 变体钉死 `torch==2.13.0` 和
per-platform 的 `sgl-kernel`。`srt_empty` 非 CUDA 基座丢掉了这两者，
`merge-runtime-base.py` 再把纯运行时闭包折进来，于是
`pip install sglang==0.5.18+flagos` 一步带齐完整运行时依赖，而不碰 torch 或
triton。

## 零 sgl-kernel

安装不携带原生 `sgl-kernel` wheel。共享的 `sgl-kernel-shim` 满足 `sgl_kernel`
import 面，硬件算子全部由 runtime 内置的 flag_gems 提供。shim 的符号从不被
调用——它的源码在 sglang-plugin-FL，不在这里。

## 一个 sdist，多个厂商

每个后端从同一个 sdist 构建，在自己的 runtime `-build` 镜像内（ascend 的
aarch64 出自 aarch64 容器）。per-vendor 差异——例如 metax 的 JIT 缺口 fallback
——是构建前在 host 侧应用的 patch，或插件层代码，绝不写进 wheel。

`+flagos` 后缀把这个 wheel 标记为我们的，使精确 pin 永不漂到官方 `0.5.18`。

## 完整理由

设计记录就在代码旁：

- [packaging/sglang/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/sglang/DESIGN.md) —— 决策，面向维护者。
- [packaging/sglang/docs/sglang-0.5.18/decisions.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/sglang/docs/sglang-0.5.18/decisions.md) —— ADR 记录（§5.1–§5.8）。
- [packaging/sglang/config.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/sglang/config.yaml) —— repack 规则，作为数据。
