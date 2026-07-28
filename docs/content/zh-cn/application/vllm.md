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

## 构建参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RUNTIME_IMAGE` | _(必填)_ | 运行时镜像引用，如 `harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.1` |
| `VLLM_VERSION` | `0.20.2` | 要安装的 vLLM 版本。该版本对应的"手术 wheel"必须已上传到 `FLAGOS_PYPI`。 |
| `FLAGOS_PYPI` | `""` | 厂商 PyPI 索引 — 存放**手术后的** vllm wheel，优先搜索。 |
| `EXTRA_PYPI` | `https://mirrors.aliyun.com/pypi/simple` | 阿里云镜像 — 其他所有依赖的回退源。 |
| `PLUGIN_FL_REF` | `""` | vllm-plugin-FL 的 git 引用（tag、分支或 commit）。 |
| `VLLM_VENDOR` | `cuda` | C++ 扩展编译的厂商标识。CUDA-ABI 后端用 `cuda`；PrivateUse1 后端用 `ascend` / `gcu`。 |

## 手术后的 vLLM wheel

官方 vLLM wheel 在 METADATA 中声明了对 torch、triton 以及 NVIDIA 独占包的
`Requires-Dist` — 直接安装会覆盖 runtime 镜像中精心编排的软件栈。我们先用
`vllm-repack/repack.py` 将这些条目从 wheel 的 METADATA 中摘除，再将手术后的
wheel 以相同版本号上传到厂商的 `FLAGOS_PYPI`。

`pip install` 时优先搜索厂商 PyPI — 找到手术后的 wheel 并使用。其余（安全）依赖
全部从 `EXTRA_PYPI` 解析。torch 和 triton 已存在于 runtime venv 中且满足所有
传递约束，pip 不会去动它们。

手术工具见 `vllm-repack/repack.py`，分类规则见 `vllm-repack/config.yaml`。

## vllm-plugin-FL

目前从源码安装（尚无发布 wheel），通过 `PLUGIN_FL_REF` 构建参数锁定 git 版本。
`VLLM_VENDOR` 参数控制编译哪个 C++ 后端。

> **TODO:** 为每个厂商构建并发布 `vllm-plugin-FL` wheel。有了 wheel 之后，
> Containerfile 将改为 `pip install` wheel 而非源码编译。

## 构建示例

```bash
docker build \
  --build-arg RUNTIME_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.1.1 \
  --build-arg FLAGOS_PYPI=https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --build-arg PLUGIN_FL_REF=main \
  -t harbor.baai.ac.cn/flagos-app/vllm-nvidia-cuda12.8:2.1.1 \
  -f app/vllm/Containerfile .
```
