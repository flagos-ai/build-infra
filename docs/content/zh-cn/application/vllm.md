---
title: vLLM
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


**vLLM 应用镜像**构建在 `flagos-runtime` 之上，打包一个可运行的 vLLM 服务
与 vllm-plugin-FL 插件。

已发布的镜像按后端拆分——镜像引用与启动方式见
[应用镜像]({{< relref "/application" >}}) 目录或各个后端的独立页面。

## 构建参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RUNTIME_IMAGE` | _(必填)_ | 运行时镜像引用，如 `harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.2` |
| `VLLM_VERSION` | `0.24.0` | 要安装的 vLLM 版本。该版本对应的"手术 wheel"（`+flagos`，见下文）必须已上传到 `FLAGOS_PYPI`。 |
| `FLAGOS_PYPI` | `""` | 厂商 PyPI 索引 — 存放**手术后的** vllm wheel，优先搜索。 |
| `EXTRA_PYPI` | `https://mirrors.aliyun.com/pypi/simple` | 阿里云镜像 — 其他所有依赖的回退源。 |
| `PLUGIN_FL_VERSION` | `""` | vllm-plugin-FL 的 wheel 版本（commit 级精确），如 `0.2.0+gcf8998c.d20260815`。从厂商 PyPI 安装；空值 = 不安装插件。非空时，镜像 tag 追加 `-{version}`（`+` → `_`）。 |
| `APP_DEPS` | `""` | 厂商条件包（configs.yaml `deps_app.vllm`），空格分隔，从厂商 PyPI 安装。 |

## 手术后的 vLLM wheel

官方 vLLM wheel 在 METADATA 中声明了对 torch、triton 以及 NVIDIA 独占包的
`Requires-Dist` — 直接安装会覆盖 runtime 镜像中精心编排的软件栈。我们先用
`packaging/vllm/repack.py` 将这些条目从 wheel 的 METADATA 中摘除，再将手术后的
wheel 以 `vllm-{version}+flagos` 名称上传到厂商的 `FLAGOS_PYPI`。

`pip install` 时优先搜索厂商 PyPI — 找到手术后的 wheel 并使用。其余（安全）依赖
全部从 `EXTRA_PYPI` 解析。torch 和 triton 已存在于 runtime venv 中且满足所有
传递约束，pip 不会去动它们。`+flagos` 标记在构建中显式锁定
（`vllm==${VLLM_VERSION}+flagos`）——裸 `vllm=={version}` 会解析到官方 wheel，
其 torch Requires-Dist 会覆盖已固定的 vendor torch。

手术工具见 `packaging/vllm/repack.py`，分类规则见 `packaging/vllm/config.yaml`。

## vllm-plugin-FL

插件以预构建 wheel（`vllm-plugin-fl==<version>`）从厂商 PyPI 安装——不在应用
镜像内做源码编译。wheel 由 vllm-plugin-wheel 工作流构建并做过依赖审计。
`PLUGIN_FL_VERSION` 构建参数锁定确切版本；非空时，发布镜像的 tag 会追加
`-{version}` 段（`+` → `_`），如 `vllm0.24.0-nvidia-cuda12.8:2.1.2-0.2.0_gcf8998c.d20260815`。

## 构建示例

```bash
docker build \
  --build-arg RUNTIME_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.2 \
  --build-arg FLAGOS_PYPI=https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --build-arg PLUGIN_FL_VERSION=0.2.0+gcf8998c.d20260815 \
  -t harbor.baai.ac.cn/flagos-app/vllm0.24.0-nvidia-cuda12.8:2.1.2-0.2.0_gcf8998c.d20260815 \
  -f app/vllm/Containerfile .
```
