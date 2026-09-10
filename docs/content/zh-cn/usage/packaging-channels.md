---
title: 打包渠道
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

FlagOS 制品如何分发：哪条渠道承载什么、仓库如何组织、软件包如何命名与定版本。该布局在
[build-infra#600](https://github.com/flagos-ai/build-infra/issues/600) 中确定；本页是编排上传工作流、
以及接入新组件时的参考。

## 两条渠道

| 渠道 | 承载内容 | 安装方式 |
|---|---|---|
| **deb/rpm 仓库**（按目标发行版划分） | 原生库（`flagcx`、`libtriton-jit`、`flagtree` 等）与纯 Python 的 FlagOS 包（`flag_gems`、`flag_attn` 等） | `apt install` / `dnf install` |
| **PyPI 索引**（按厂商划分：`flagos-pypi-<vendor>`） | 一切与厂商工具链绑定的东西：厂商定制 torch（`torch==X.Y.Z+musa`）、厂商算子包（`torch_musa`、`torch_npu` 等）、二进制算子扩展（`flag_gems_cpp_<vendor>`） | `pip install --index-url .../flagos-pypi-<vendor>/simple ...` |

**边界规则：一个包走 deb/rpm，当且仅当发行版渠道确实能承载它。**

纯 Python（arch:all / noarch）包满足这一条件。一次构建即可服务所有 suite，其依赖稳定，
而正是原生交付才让**整个技术栈**可以通过发行版仓库交付：要进入 openEuler / openKylin /
deepin 的官方仓库，整条依赖闭包都必须是原生包；而隔离网或受合规管控的机器只通过发行版包管理器
安装与打补丁，所以一条 `dnf install` 必须能解析整个技术栈，包括 Python 层。

与厂商工具链绑定的二进制则不行：

- (python x torch x SDK x distro) 的版本矩阵无法用 deb/rpm 命名表达，而 pip 的环境标记与
  按厂商分立的索引可以自然处理；
- 若干厂商 SDK 不可再分发，因此公开的 deb/rpm 既不能携带、也不能依赖它所需的运行时；
- 这些 wheel 有 GB 级体积且迭代很快；
- 两个同名同版本的制品（`torch==2.9.1+musa` 与上游 `torch==2.9.1`）根本无法共存于同一个
  apt/yum suite —— 在 pip 侧，按厂商分立的索引 URL 就是区分依据，因此没有工具需要靠元数据
  去分辨同名的 wheel。

deb/rpm 从不取代 PyPI 渠道；两者并存。deb/rpm 一侧必须能独立安装：**不得有硬依赖指向 pip 层。**
桥接是软的 —— 安装文档指向厂商 pip 索引，或者由某个元包的 `Recommends`/描述来指。

## 仓库布局

- **apt**：每个目标发行版版本一个 hosted 仓库
  （`flagos-apt-<distro><ver>`）。一个 apt-hosted 的 Nexus 仓库只承载一个
  distribution，且 apt 没有 group 仓库。
- **yum**：一个 hosted 仓库，按子路径划分 repodata：
  `flagos-yum-hosted/<distro>/<ver>/<arch>/`，例如 `openeuler/24.03/x86_64`、
  `fedora/43/x86_64`。
- **arch:all / noarch 包会被复制进它适用的每一个 suite** —— 不存在单独的 "shared" 仓库。
  用户只需一行 sources，而各 suite 的依赖下限（例如不同的 sqlalchemy 最低版本）仍然可表达。

## 版本

- deb：在 Debian revision 上加发行版后缀 `+<distro><ver>`
  （`0.6.0-1+ubuntu22.04`）—— 它排序高于无后缀的 revision，可以干净地升级无后缀的包。
- rpm：`%{?dist}`（`.oe2403`、`.fc43`、`.el9`）—— 在目标发行版容器内构建时自动展开，
  否则显式传入。
- 包版本跟随上游 tag；构建脚本必须从打包元数据读取版本，绝不硬编码。

## 命名

- 原生库，每个平台一个包：`libflagcx-<platform>`、
  `libtriton-jit-<vendor>`、`python3-flagtree-<backend>`。平台与后端名沿用上游标识符。
- 同一组件的同平台包在不同后端之间互斥：deb 用 `Conflicts`；rpm 靠共享 soname 的文件冲突。
- 纯 Python 包：`python3-<upstream-name>`，不改动上游源码。

## 厂商库依赖

按 (distro x component) 逐个选择，顺序如下：

1. **原生** —— 发行版本身、或厂商针对该发行版的官方仓库提供了该库的 RPM/deb：声明常规依赖。
   例：Fedora 43 上的 CUDA，走 NVIDIA 的 fedora 仓库。
2. **部分原生** —— 只有部分库有提供者：只排除缺失的那些。例：Fedora 43 上
   `external_ccl_runtime` 只排除 `libnccl.so.2`（NCCL 没有 Fedora RPM）。
3. **无提供者** —— 完全排除厂商库（`external_vendor_runtime`，如 openEuler 上）；
   部署环境提供 ABI 兼容的库，通常通过厂商 pip 索引。

在版本下限有意义的地方，显式的带版本依赖（`Requires: libnccl >= 2.27`）与自动生成的
soname 依赖并存。

## 本轮不涉及 / 后续

- 模型层仓库（FlagScale、slang、megatron、verl 等）目前不打包为 deb/rpm。
- 自解压离线包（toolkit 风格：本地仓库 + 安装脚本）后续可以由同一套 per-suite 仓库生成，
  用于隔离网交付。它叠加在本设计之上，不改变本设计。
