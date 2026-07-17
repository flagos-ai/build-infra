---
title: "基础镜像（base）"
weight: 20
---

**基础镜像**是在操作系统之上安装厂商 SDK 与工具链。它只关乎**操作系统**和
**支持的 SDK 版本**——与 Python、Torch、Triton 无关（那些属于
[运行时镜像]({{< relref "/runtime" >}})）。

选择一个后端，查看它的内容（操作系统、SDK 包、环境变量）以及如何运行：

{{< base-catalog >}}
