---
title: 升级 uv
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

`runtime/Containerfile` 固定了特定的 uv 版本，并从内部文件存储下载。uv 用于
创建虚拟环境和安装所有 Python 包。

## 为什么 uv 和 CPython-standalone 要联动更新

当 Containerfile 中有 `uv venv --python 3.11` 且基础镜像没有 Python 3.11 时，
uv 会从 [python-build-standalone][pbs] 下载独立的 CPython 构建。uv 使用的
release tag **硬编码在 uv 二进制中**——每个 uv 版本绑定到固定的 tag。更新 uv
→ tag 变化 → 文件存储中缓存的 tarball 必须同步更新。

[pbs]: https://github.com/astral-sh/python-build-standalone/releases

| uv 版本  | python-build-standalone release tag |
|---|---|
| 0.11.30 | `20260718`                          |

## 如何找到新的 release tag

将新版 uv 二进制下载到任意 runner 后：

```bash
# 方法一：快速 — 从二进制中 grep
strings uv | grep -oE 'cpython-[0-9.]+%2B[0-9]+-[a-z0-9_-]+-install_only[^"]*\\.tar\\.gz' | sort -u

# 方法二：精确 — 强制重装并查看日志
uv python install --reinstall --no-cache -v cpython-3.11.15-linux-$(uname -m)-gnu 2>&1 | grep Downloading
# → https://releases.astral.sh/github/python-build-standalone/releases/download/<TAG>/...
```

## 需要镜像的文件

每个 tag 需要下载 `*_stripped` 变体（体积更小），涵盖项目使用的 Python
小版本和架构。三个版本（3.10、3.11、3.12）× 两种架构（x86_64、aarch64）=
**每个 tag 6 个文件**。

上传到：

```
flagos-filestore/uv-python/<TAG>/<filename>
```

## Containerfile 修改

- 修改 `runtime/Containerfile` 中 `curl` 行的 uv 版本号。
- `UV_PYTHON_INSTALL_MIRROR` 环境变量（见下文）无需更改——uv 内部自动拼接 tag 路径。

## 镜像加速（2026-07-24 已配置）

`UV_PYTHON_INSTALL_MIRROR` 让 uv 从文件存储下载 CPython 而不是从 GitHub。
待 6 个文件上传后，在 Containerfile 的 `uv venv` 之前添加：

```dockerfile
ENV UV_PYTHON_INSTALL_MIRROR=https://resource.flagos.net/repository/flagos-filestore/uv-python
```

在镜像配置好之前，uv 会回退到 GitHub 下载，在国内 runner 上会很慢。
