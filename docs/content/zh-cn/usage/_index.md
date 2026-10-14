---
title: "使用镜像"
weight: 50
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


## 拉取

镜像名和 tag 见各后端页面，位于[基础镜像]({{< relref "/base" >}})和
[运行时镜像]({{< relref "/runtime" >}})下。例如：

```bash
docker pull harbor.baai.ac.cn/flagbase/flagos-base-nvidia-cuda12.8:2.1.0-0
```

## 镜像内预置了什么

每个 base 镜像都用 `ENV` 直接烘焙了厂商 SDK 环境（`PATH`、`LD_LIBRARY_PATH` 以及
厂商特有的变量）——你无需 source 任何脚本。具体变量以及一条可直接复制的
`docker run` 命令，都在每个镜像的页面上。

## 指定 FlagTree 版本

运行时镜像和 app 镜像默认使用 FlagTree 作为编译器（`/flagos` 是 Python 环境，
FlagTree 位于 `/opt/flagtree`）。FlagTree 版本发布频繁，重建 runtime 意味着
其上所有 app 镜像都要跟着重建——因此可以在启动容器时直接指定版本：

```bash
docker run -e FLAGTREE_VERSION=0.7.0 <runtime 或 app 镜像> ...
```

指定的 wheel 会在应用启动前安装到 `/opt/flagtree`，同一容器内的后续 shell
直接复用。`-e FLAGTREE_VERSION=0.7.0` 会安装本后端为该版本发布的那一个——
通常是带 `+<后端>3.6` 后缀的构建。写全带 `+` 后缀的版本号即可指定具体某个构建。容器已在运行时，
可以执行 `compiler flagtree <版本>` 达到同样效果。单独执行 `compiler` 查看当前
版本，`compiler triton` 切换到厂商 Triton。

## 按需构建

base 镜像是手动构建的，不会每次变更都触发（厂商 SDK 变更不频繁）：

- **CI：** 运行 **Base Image Build (manual)** GitHub Actions 工作流
  （`workflow_dispatch`）——选择一个后端（或 `all`）以及是否推送。
- **本地：** `python base/build.py <vendor>-<backend> [--push]`（会从
  `.github/build-config.yml` 读取镜像仓库地址）。
