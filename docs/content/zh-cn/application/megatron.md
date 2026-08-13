---
title: Megatron
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


**Megatron 应用镜像**构建在 `flagos-runtime` 之上，打包可用的 megatron-core
库，用于 megatron-lm 训练栈。

## 构建参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RUNTIME_IMAGE` | _(必填)_ | 运行时镜像引用，如 `harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2` |
| `MEGATRON_VERSION` | `0.17.1` | 要安装的 megatron-core 版本。该版本对应的"手术 wheel"必须已上传到 `FLAGOS_PYPI`。 |
| `FLAGOS_PYPI` | `""` | 厂商 PyPI 索引 — 存放**手术后的** megatron-core wheel，优先搜索。 |
| `EXTRA_PYPI` | `https://mirrors.aliyun.com/pypi/simple` | 阿里云镜像 — 其他所有依赖的回退源。 |

## 手术后的 megatron-core wheel

megatron-core 的直接依赖面极小（`torch>=2.6.0`、`numpy`、`packaging>=24.2`），
其中唯一真正的风险点是 `torch`：若运行时 torch < 2.6.0，pip 会拉公有 PyPI 的
torch 覆盖厂商构建。我们用 `megatron-repack/`（复用 `vllm-repack/repack.py`）
将 `Requires-Dist: torch` 从 wheel 的 METADATA 中摘除，再以 `+flagos` 版本后缀
上传到厂商的 `FLAGOS_PYPI`。

`pip install` 时优先搜索厂商 PyPI — 找到手术后的 wheel 并使用。其余（安全）依赖
全部从 `EXTRA_PYPI` 解析。torch 已存在于 runtime venv 中且满足所有传递约束，
pip 不会去动它。安装是**单步** `pip install`（无 `--no-deps`）。

wheel 本身由 `megatron-builder/` 从 Megatron-LM-FL fork 构建（cp310/cp311/cp312
三个 ABI 专属 wheel；fork 的 `requires-python >=3.12` 在构建时 on-the-fly 放宽
到 `>=3.10`）。分类规则见 `megatron-repack/config.yaml`。

## 构建示例

```bash
docker build \
  --build-arg RUNTIME_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2 \
  --build-arg FLAGOS_PYPI=https://resource.flagos.net/repository/flagos-pypi-hygon/simple \
  -t harbor.baai.ac.cn/flagos-app/megatron-hygon-dtk26.04:2.1.2 \
  -f app/megatron/Containerfile .
```
