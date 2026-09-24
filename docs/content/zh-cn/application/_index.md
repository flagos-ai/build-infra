---
title: "应用镜像（application）"
weight: 40
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


**应用镜像**构建在[运行时镜像]({{< relref "/runtime" >}})之上，把一个开箱即用的
AI 应用与 FlagOS 软件栈打包在一起。每个应用都按后端发布镜像，每个镜像都有独立的
页面，说明镜像引用、前置条件与启动方式。

应用镜像以**通用厂商**命名，不带芯片品牌（如 `generic-12.8`）；基础镜像与运行时
镜像保留真实厂商名。每个页面「基于」一行指向该应用构建所用的运行时镜像，用的是
它的真实名称。

选择一个应用和后端，查看它的启动方式：

{{< app-catalog >}}
