---
title: FlagTree
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


FlagTree（Triton fork）是运行时镜像与 app 镜像的默认编译器。它从源码构建为
per-backend 的 wheel，而不是从厂商的 wheel 安装。

## 为什么从源码构建

厂商的 wheel 带着一些只有源码构建才能消除的缺陷：

- **旧的 glibc 链接** —— MetaX 的 wheel 构建于 Ubuntu 24.04，`libtriton.so`
  链接了 `GLIBC_2.38`/`GLIBCXX_3.4.32`，在 22.04 节点上 `main()` 之前就中止。
- **debug 冗余** —— 当前 MetaX wheel 的 `libtriton.so` 带 793.7 MB 的 debug
  段，本仓库的 release 构建约 218 MB。
- **无来源信息** —— 厂商 wheel 不携带 `Source-Commit`。

源码构建还提供了一条与厂商 wheel 对比的 A/B 基线。

## 构建形态

每个后端在 `packaging/flagtree/backends.yaml` 旁各有一个 Containerfile（11 个
后端）。构建拆成两个阶段：

- **`--target builder`** —— 与 FlagTree ref 无关的一切：apt 工具链、解释器，
  以及预置进 FlagTree 离线缓存的 LLVM/plugin/triton 工具包。该阶段会被发布，
  因此热构建只需为 clone 和编译买单。
- **default target** —— clone ref 并在已发布阶段之上编译。

九个后端从裸 `ubuntu:22.04` 起步（旧 glibc，`libtriton.so` 得以在 22.04 节点
加载）；ascend 一对从各自的运行时镜像起步，因为 Ascend 构建需要 CANN 在
构建机上。

两道硬门禁支撑「可复现」这一说法：objdump 门禁在任何 22.04 不兼容符号上使
构建失败，smoke 测试则要求携带 `Source-Commit` 元数据。

## 每日线

每日工作流为每个后端每天发布一个 wheel，作为**独立的发行名**
（`flagtree-nvidia`、`flagtree-metax`、……）。版本是
`<version_base>.dev<UTC 日期>`，放在公共段，因此普通的 `pip install flagtree`
仍会解析到 release，而「最新 daily」只是纯版本比较。

某个 daily 是从哪个 commit 构建的，记在它的元数据里
（`Project-URL: Source-Commit`），从不在文件名里。

## 完整理由

- [packaging/flagtree/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagtree/DESIGN.md) —— 面向维护者的决策记录。
- [packaging/flagtree/README.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagtree/README.md) —— 每个 builder 的用法，按后端展开。
- [packaging/flagtree/backends.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagtree/backends.yaml) —— 构建线事实。
