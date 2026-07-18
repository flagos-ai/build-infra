---
title: "运行时镜像（runtime）"
weight: 30
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


**运行时镜像**构建在[基础镜像]({{< relref "/base" >}})之上，加入 **Python 解释器**
和**软件栈**——Torch、Triton、FlagTree 以及 FlagGems。

选择一个后端，查看它的 Python 版本、软件栈、依赖以及如何运行：

{{< runtime-catalog >}}
