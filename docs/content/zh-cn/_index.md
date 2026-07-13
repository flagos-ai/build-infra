---
title: Release Info
type: docs
---

# Release Info

FlagOS 容器镜像构建基础设施。FlagOS 的镜像是分层发布的——厂商 **base** 镜像、
其上的 FlagGems **runtime** 镜像，以及（即将推出的）**application** 镜像。

- **[概览]({{< relref "overview" >}})** —— 各镜像层如何关联与命名。
- **[基础镜像]({{< relref "base" >}})** —— 操作系统 + 厂商 SDK。每个后端的内容与运行命令。
- **[运行时镜像]({{< relref "runtime" >}})** —— Python + 软件栈（torch、triton、flagtree、FlagGems）。
- **[应用镜像]({{< relref "application" >}})** —— vLLM、Megatron-LM、SGLang（规划中）。
- **[使用]({{< relref "usage" >}})** · **[贡献]({{< relref "contribution/onboarding" >}})**

本文档中的所有事实信息都由 `configs.yaml` + `base/` 自动生成，因此不会与源头脱节。
