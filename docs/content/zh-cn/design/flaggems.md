---
title: FlagGems
weight: 40
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


FlagGems 是 FlagOS 镜像里 vLLM 所运行的算子库。它按一个关键事实分成三条
发布通道——`flag_gems` 包是纯 Python，C++ 算子库则不是：

- **`flag_gems` wheel** —— `py3-none-any`，因此不需要厂商工具链、不携带
  glibc floor。同一个 wheel 上传到所有厂商 PyPI。
- **`flag_gems_cpp_<backend>` wheel** —— 每个后端的 C++ 算子，在
  runtime 镜像（`{version}`）内构建，其 venv 已带 torch + 依赖 +
  编译器。每个 cmake backend 一个，上传到该后端的厂商索引。
- **`python3-flag-gems` `.deb`** —— 用上游自带的 `packaging/debian/` 定义构建；
  build-infra 只拥有发布路径。

## 为什么 python wheel 不需要容器

`py3-none-any` 是平台无关的，所以构建就是一个普通脚本：带 tag clone
FlagGems、`pip wheel . --no-deps`，再加一道门禁——结果必须是 `py3-none-any`，
出现平台 tag 就大声失败（那意味着构建误入了 C++ 后端）。

版本是 FlagGems 自己的，由 `setuptools_scm` 从它的 git tag 读取。每日
（非 tag）构建会打一个一次性本地 tag，让 `_version.py` 仍携带真实 commit，
随后工作流上传到 `flagos-pypi-daily`。

## 为什么 cpp wheel 在 runtime 镜像里构建

C++ 算子要对着 torch 和厂商后端编译，所以构建环境必须等于交付环境——与
vllm-plugin-FL 原生 wheel 同一条规则。runtime 镜像（`{version}`）已经带了
torch、依赖和编译器，于是 `pip wheel ./cpp` 在里面直接可用。

哪些后端有这个 wheel 是**推导**出来的，不是枚举：`cpp_matrix.py` 把 runtime
矩阵过滤到 `configs.yaml` 里设了 `cmake_backend` 的行，`VENDOR_MAP` 再把它
转成 wheel 的名字 token（`cuda`、`npu`、`gcu`、`ix`、`musa`）。

## 为什么 deb 留在上游

`packaging/debian/` 定义是上游的，也留在上游——那是发行版维护者会去找的
地方。build-infra 只拥有*发布路径*（clone → 构建 → 验证 → 发布），所以产出
包不依赖组件仓库里的改动落地。包是 `Architecture: all`，一个产物发布进每个
apt suite。

## 完整理由

设计记录就在代码旁：

- [packaging/flaggems/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaggems/DESIGN.md) —— 决策，面向维护者。
- [packaging/flaggems/build.sh](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaggems/build.sh) —— python wheel 构建。
- [scripts/release_flaggems.py](https://github.com/flagos-ai/build-infra/blob/main/scripts/release_flaggems.py) —— 发布路径（build/upload/update-config）。
- [scripts/cpp_matrix.py](https://github.com/flagos-ai/build-infra/blob/main/scripts/cpp_matrix.py) —— 哪些后端构建 cpp wheel。
