---
title: FlagLibs
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


FlagLibs 把 FlagOS 的**算子库**（FlagAttention、FlagSparse、FlagBLAS、
FlagAudio、FlagFFT、FlagGems-vllm、FlagGems-sglang）发布为可安装的 wheel。
它们全都是纯 Python，这决定了整条线：wheel 是 `py3-none-any`，所以没有厂商
工具链、没有容器、也没有 glibc floor——一个普通 venv 脚本就能把它们全部构建。

## 为什么是单个 hosted 索引，而非 per-vendor

per-vendor 索引（`flagos-pypi-<vendor>`）的存在是为了分隔厂商绑定的二进制
——链接特定工具链的 wheel（`flag_gems_cpp`、`torch_musa` 等）。这些库不带
设备二进制（后端适配由 Triton JIT 在运行时提供），因此单次发布到
`flagos-pypi-hosted` 就能服务所有厂商的 runtime。

## 版本就是构建 ref

每个 wheel 的版本是它构建 ref 的纯函数：上游 release tag（`v0.4.0` →
`0.4.0`）。build-infra 不合成任何版本号——不同于 flagcx wheel 的 `+<backend>`
本地标签（那个标签的存在是为了区分两个厂商同一 commit 的构建）。这里每个库
只有一个 wheel，tag 单独就够了。

有一个库 `flag_attn` 由 `setuptools_scm` 按 git tag 出版本，因此需要带 tag 的
全量 clone（浅 clone 会退化成 `0.0.0`）；其余是 pyproject 静态版本，浅 tag
checkout 即可。

## 只在 CI 构建

构建脚本可在本地跑（dry-run 调试），但发布动作只在 GitHub Actions
（`flaglibs-wheel.yml`，manual dispatch，`check-trigger-author` 守门）——与
flagtree、flaggems 同一纪律。

## 完整理由

设计记录就在代码旁：

- [packaging/flaglibs/docs/decisions.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaglibs/docs/decisions.md) —— 决策记录（D1–D7）。
- [packaging/flaglibs/build-config.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaglibs/build-config.yaml) —— 库清单：仓库、默认 ref、版本来源。
- [packaging/flaglibs/build.sh](https://github.com/flagos-ai/build-infra/blob/main/packaging/flaglibs/build.sh) —— 构建。
