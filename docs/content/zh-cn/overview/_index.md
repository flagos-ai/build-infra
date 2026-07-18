---
title: 概览
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


FlagOS 镜像是分层的。每一层都构建在下一层之上，各有其关注点。

## base（基础镜像）

在操作系统之上安装厂商的 SDK/工具链。基础镜像**只**关乎：

- **基础操作系统**（containerfile 的 `FROM`），
- **支持的 SDK 版本**（后端名，如 `cuda12.8`、`cann9.0.0`），
- 以及其上安装的**内容**（系统包 + 厂商 SDK 包）。

它与 Python、Torch、Triton 的版本**毫无关系**——那是运行时的事。由
`base/build.py` 从 `base/<vendor>-<backend>` 构建，打标签为
`flagos-base-<vendor>-<backend>:<version>-<revision>`。

## runtime（运行时镜像）

构建在基础镜像之上；加入 **Python 解释器**与**软件栈**（Torch、Triton、FlagTree、
FlagGems）。由 `runtime/build.py` 构建，镜像 `flagos-runtime-<vendor>-<backend>`。

## application（应用镜像，未来）

构建在运行时镜像之上；打包一个开箱即用的应用（vLLM、Megatron-LM、SGLang……）。

## 镜像仓库与事实源

所有镜像推送到 `.github/build-config.yml` 里配置的同一个镜像仓库，各层只在路径
前缀上不同。`configs.yaml` 保存每个后端的依赖和环境；`base/<name>` containerfile
承载操作系统 + SDK。本文档里的目录和每镜像页都由这些文件生成。
