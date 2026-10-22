---
title: 设计
weight: 55
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


FlagOS 构建与打包方式背后的设计决策——*为什么*某个 wheel 这样打标签、某个
构建这样成型，而不只是*产出*了什么。

这些页面是面向使用者的简短摘要。完整理由记录在它所描述的代码旁（对应
`packaging/` 或 `docs/` 目录下的 `DESIGN.md`）；每页都会链接过去。事实源是
仓库内文件，不是本网站。

- **[vllm-plugin-FL]({{< relref "vllm-plugin-fl" >}})** —— 原生 `vllm_fl._C`
  wheel、其裸后端名标签方案，以及为何在运行时镜像内构建而非使用 builder 镜像。
- **[FlagTree]({{< relref "flagtree" >}})** —— 从源码构建的 per-backend 编译器
  wheel、`--target builder` 阶段拆分，以及每日线。
- **[FlagCX]({{< relref "flagcx" >}})** —— 集合通信库的 deb/wheel/builder 三条
  通道、每个后端一个产物的规则，以及 glibc floor。
- **[FlagGems]({{< relref "flaggems" >}})** —— 纯 Python 的 `flag_gems` wheel、
  每个后端的 cpp wheel，以及上游自有的 deb。
- **[FlagLibs]({{< relref "flaglibs" >}})** —— 算子库，每个库一个 `py3-none-any`
  wheel，发布到单个 hosted 索引。
