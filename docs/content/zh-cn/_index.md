---
title: build-infra
type: docs
---

# build-infra

FlagOS 容器镜像构建基础设施。本仓库定义并构建 **base 镜像**——在操作系统之上叠加
厂商 SDK 与工具链——FlagOS 的运行时镜像正是构建在这些 base 镜像之上。

- **[概览]({{< relref "overview" >}})** —— 镜像如何分层与命名。
- **[镜像]({{< relref "images" >}})** —— 支持的厂商/后端目录，以及每个镜像的参考
  （装了什么、设了哪些环境变量、带哪些依赖）。
- **[使用]({{< relref "usage" >}})** —— 如何拉取与运行镜像。
- **[贡献]({{< relref "contribution/onboarding" >}})** —— 如何接入一个新的厂商/后端。

本文档中的所有事实信息都由 `configs.yaml` + `base/` 自动生成，因此不会与源头脱节。
