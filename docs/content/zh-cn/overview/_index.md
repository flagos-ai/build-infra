---
title: 概览
weight: 10
---

# 概览

## 镜像分层

- **base** —— 在操作系统之上叠加厂商 SDK/工具链 + Python 工具链。由
  `base/build.py` 从 `base/<vendor>-<backend>` 构建，打标签为
  `flagos-base-<vendor>-<backend>:<version>-<revision>`（version/revision 取自
  containerfile 的 OCI label）。
- **runtime** —— 在 base 镜像之上安装 FlagGems（单独的流程）。
- **app** —— 应用层（未来）。

## 命名与镜像仓库

所有镜像推送到 `.github/build-config.yml` 里配置的**同一个镜像仓库**，各层之间只在
服务器上的**路径前缀**不同（base 镜像用 `flagbase`）。

## 事实源

`configs.yaml` 保存每个后端的依赖和镜像环境；每个 `base/<name>` containerfile 承载
操作系统 + SDK 安装以及 OCI version/revision label。本文档里的目录和每镜像参考都由
这些文件生成，因此始终与实际构建一致。
