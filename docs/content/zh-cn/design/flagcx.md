---
title: FlagCX
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


FlagCX 是集合通信库（类 NCCL）。build-infra 通过三条通道发布它，一个后端
一个容器，三条通道共读一个 `backends.yaml`：

- **`.deb`** —— `libflagcx-<backend>` / `-dev` 成对，发布到以其基础镜像
  Ubuntu 版本命名的 apt 仓库（`flagos-apt-ubuntu24.04` / `-22.04`），用户按
  发行版添加仓库即可，永远不必知道 glibc floor 的存在。
- **wheels** —— 每个后端一个 wheel，发布到厂商 PyPI，以精确 pin 安装
  （`flagcx==0.14.0+cuda12.8`）。pip 没有 `Provides:`，精确 pin 正是阻止两个
  厂商同一 commit 的构建互相顶替的机制。
- **builder 镜像** —— 自包含的 `ubuntu:22.04` 工具链镜像，服务那些 wheel
  至多只能链接 glibc 2.35（从而能装到实体 22.04 主机上）的行，以及那些
  runtime 镜像完全不携带设备工具链的行。

## 为什么每个后端一个产物

该库链接厂商的 CCL 与设备头文件，各后端不同，因此构建按 `{vendor}-{backend}`
键寻址。deb 线因此每个后端一个包；wheel 线同理，因为 pip 无法表达「默认
变体回应非限定名」。

芯片（910B vs 910C、`sm_90` vs `sm_120`）刻意**不**作为构建输入：设备由驱动
在运行时选择，所以一个 wheel 同时服务某后端的两款芯片。

## 版本标签与 pin

wheel 的本地版本标签是裸后端名（`+cuda12.8`、`+maca3.7.2.1`、`+dtk2604`），
去掉 `{vendor}-` 前缀——wheel 本就落到按厂商划分的索引里。标签放在本地段的
开头，使版本范围不会跨进另一后端的变体；每次安装都用 `==` 而非 `>=`。

## glibc floor 从何而来

deb 线按发行版寻址（基础镜像的 Ubuntu 版本）。wheel 线需要一个 runtime 镜像
未必能给出的 floor：24.04 的 runtime 链接 GLIBC 2.38，在离线 bundle 所安装
的实体 22.04 主机上会中止。builder 通道靠自包含 `ubuntu:22.04` 解决——自带
解释器、torch pin 与 SDK——于是 floor 降到 2.35，且不动 runtime 或 FlagTree。
该 floor 在产物处断言（基于 `objdump`），而不是记成一个镜像 digest。

## 完整理由

设计记录就在代码旁：

- [packaging/flagcx/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagcx/DESIGN.md) —— deb 线的决策。
- [packaging/flagcx/WHEEL-DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagcx/WHEEL-DESIGN.md) —— wheel 与 builder 线的决策。
- [packaging/flagcx/backends.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagcx/backends.yaml) —— 每个后端的打包事实。
