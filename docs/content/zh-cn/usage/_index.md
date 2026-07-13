---
title: 使用
weight: 30
---

# 使用镜像

## 拉取

镜像名和 tag 见[目录]({{< relref "images" >}})。例如：

```bash
docker pull harbor.baai.ac.cn/flagbase/flagos-base-nvidia-cuda12.8:2.1.0-0
```

## 镜像内预置了什么

每个 base 镜像都用 `ENV` 直接烘焙了厂商 SDK 环境（`PATH`、`LD_LIBRARY_PATH` 以及
厂商特有的变量）——你无需 source 任何脚本。每个镜像的具体变量见
[每镜像参考]({{< relref "images/reference" >}})。

## 按需构建

base 镜像是手动构建的，不会每次变更都触发（厂商 SDK 变更不频繁）：

- **CI：** 运行 **Base Image Build (manual)** GitHub Actions 工作流
  （`workflow_dispatch`）——选择一个后端（或 `all`）以及是否推送。
- **本地：** `python base/build.py <vendor>-<backend> [--push]`（会从
  `.github/build-config.yml` 读取镜像仓库地址）。
