---
title: "基础镜像（base）"
weight: 20
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


**基础镜像**是在操作系统之上安装厂商 SDK 与工具链。它只关乎**操作系统**和
**支持的 SDK 版本**——与 Python、Torch、Triton 无关（那些属于
[运行时镜像]({{< relref "/runtime" >}})）。

选择一个后端，查看它的内容（操作系统、SDK 包、环境变量）以及如何运行：

{{< base-catalog >}}
