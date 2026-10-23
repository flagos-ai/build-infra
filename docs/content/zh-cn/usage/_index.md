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

FlagTree 是运行时镜像和 app 镜像的默认编译器，版本发布频繁。启动容器时即可
指定版本，无需重建镜像：

```bash
docker run -e FLAGTREE_VERSION=0.7.0 <runtime 或 app 镜像> ...
```

指定的 wheel 会在应用启动前安装到 `/opt/flagtree`。容器运行中可执行
`compiler flagtree <版本>` 达到同样效果；`compiler` 查看当前版本。

`latest` 取该后端的**最新每日构建**，而不是发布版：

```bash
docker run -e FLAGTREE_VERSION=latest <runtime 或 app 镜像> ...
```

每日 wheel 领先于下一个发布版、每天构建一次，因此这是跑上尚未发布的修复的办法。
它会下载约 120 MB，需要容器启动时能出网；每个容器只取一次，同容器内后续 shell
直接复用，下一个容器再取新发布的。

**指定的版本装不上时，容器直接起不来。** 跑着不是你要的那个 FlagTree 的容器，
并不是你要的东西，而下游没有任何东西会告诉你——所以请求被拒绝：原因写到 stderr，
退出码非零。`docker run` 返回 1；在 kubernetes 下 pod 进入 `Error`（进而
`CrashLoopBackOff`），而不是带着错的编译器 Running，原因在
`kubectl logs <pod>`（重启过就加 `--previous`）。没有每日线的后端（目前
cambricon、spacemit、thead）同样被拒绝。索引不通由一次短探测（10 秒）判定，
所以大约十秒就有结论，而不是等 pip 自己重试完。

## 按需构建

base 镜像是手动构建的，不会每次变更都触发（厂商 SDK 变更不频繁）：

- **CI：** 运行 **Base Image Build (manual)** GitHub Actions 工作流
  （`workflow_dispatch`）——选择一个后端（或 `all`）以及是否推送。
- **本地：** `python base/build.py <vendor>-<backend> [--push]`（会从
  `.github/build-config.yml` 读取镜像仓库地址）。
