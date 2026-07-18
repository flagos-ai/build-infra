---
title: 厂商接入
weight: 10
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


# 厂商接入

如何把一个新的厂商/后端接入 FlagOS base 镜像流水线。你需要提供：

1. 一个 **base containerfile** —— `base/<vendor>-<backend>`
2. `configs.yaml` 里的一个 **后端条目**（依赖 / 构建设置）
3. *（可选）* `.github/build-config.yml` 里的一个 **runner 覆盖项**

合并后，由维护者按需构建镜像。不需要每个厂商单独的 JSON 或矩阵脚本——构建矩阵由
`configs.yaml` + `base/` 推导得到。

## 流水线如何工作

- `base/generate_matrix.py` 读取 `configs.yaml`，为每个存在 `base/<vendor>-<backend>`
  文件的后端生成一个构建矩阵条目（没有该文件的后端会被跳过）。`runson` 和镜像仓库
  地址来自 `.github/build-config.yml`。
- `.github/workflows/trigger.yml` 是**手动**（`workflow_dispatch`）构建：选择一个
  后端（或 `all`）以及是否推送。
- 每个条目运行 `python base/build.py <vendor>-<backend> [--push]`，它会从
  `.github/build-config.yml` 读取镜像仓库地址、从 containerfile 的 OCI label 读取
  version/revision，并把镜像打标签为
  `flagos-base-<vendor>-<backend>:<version>-<revision>`。

## 命名

| 项目               | 约定                                                     |
|--------------------|----------------------------------------------------------|
| Base containerfile | `base/<vendor>-<backend>`（如 `base/nvidia-cuda12.8`）   |
| 镜像 tag           | `flagos-base-<vendor>-<backend>:<version>-<revision>`    |
| configs.yaml 键    | `vendors.<vendor>.<backend>`                             |

`<backend>` 段是 SDK/工具链版本（如 `cuda12.8`、`cann9.0.0`、`neuware4.4.3`），
且必须在 `base/` 文件名和 `configs.yaml` 键之间保持一致。

## 第 1 步 —— 添加 base containerfile

参照已有的（如 `base/nvidia-cuda12.8`）创建 `base/<vendor>-<backend>`。它**必须**
包含以下 OCI label：

```dockerfile
LABEL org.opencontainers.image.authors="FlagOS contributors"
LABEL org.opencontainers.image.version="<version>"
LABEL org.opencontainers.image.revision="<revision>"
```

- `version` / `revision` 生成镜像 tag `…:<version>-<revision>`。
- 每次修改已有 containerfile 都要**递增 `revision`**——改了 `base/` 文件却不递增的
  PR 会被 `check-revision` 检查拦下。新文件从 `revision="0"` 开始。
- 尽量用 `ENV` 直接烘焙厂商 SDK 环境（不要求用户 source 脚本）。只有当 `FROM` 镜像
  本身已设置 `LD_LIBRARY_PATH` 时（如 `nvcr.io/nvidia/cuda`）才追加
  `:${LD_LIBRARY_PATH}`；纯 `ubuntu:*` 基础镜像没有该变量，无需追加。

## 第 2 步 —— 添加 configs.yaml 条目

在 `configs.yaml` 里对应的厂商下添加后端。完整字段说明见该文件的头部注释。最小形态：

```yaml
vendors:
  <vendor>:
    <backend>:
      extras: <flaggems-pyproject-extra>   # 如 nvidia-cuda128
      python: "3.12"
      triton: triton==...
      # flagtree / cmake_backend / deps / env 按需填写
```

## 第 3 步 —— runner（仅在需要时）

base 镜像默认在 `ubuntu-latest` 上构建。如果某个后端需要特定架构或硬件（如
`ascend` 的包是 `aarch64`），在 `.github/build-config.yml` 的 `runners.overrides`
下添加覆盖项：

```yaml
runners:
  overrides:
    <vendor>-<backend>: [self-hosted, <label>...]
```

## 第 4 步 —— 开 PR，然后构建

带上新的 `base/` 文件和 `configs.yaml` 条目开一个 PR。合并后，由维护者通过
**Base Image Build (manual)** 工作流（`workflow_dispatch`）按需构建镜像——选择你的
后端以及是否推送。base 镜像不会在每次变更时自动构建。
