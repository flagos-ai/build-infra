# vllm 0.24.0 repack — 相比 0.20.2 的变化（Playbook）

> 本文对应原报告 §2（0.24.0 相比 0.20.2 的变化，只列影响打包的部分）与附录（验证命令）。
> 完整标准流程（empty 构建 + `+flagos` + 单步安装）见
> [vllm-0.20.2/playbook.md](../vllm-0.20.2/playbook.md)；
> 版本推进协作问题见 [decisions.md](decisions.md)，后端验证记录见 [backends/](backends/)。

## 2. 0.24.0 相比 0.20.2 的变化（只列影响打包的部分）

1. **引入两个 Rust 组件**：一个独立的前端进程（`vllm-rs`）和一个 Python 扩展
   （`vllm._rust_tool_parser`）。这两个组件默认关闭（使用 `VLLM_USE_RUST_FRONTEND=0`）。
   关闭时 vLLM 会忽略它们。只有服务 MiniMax M3 模型且开 tool calling 才会被 import。
   在不服务该模型的情况下，不会被触发。但**构建环境必须装 `setuptools-rust>=1.9.0`**
  （setup.py 无条件 import 它，缺了直接报错）；容器里没有 cargo（Rust 编译器）没关系，
   扩展声明为 optional，会被静默跳过，wheel 照常生成。

2. **empty wheel 绑定 Python 版本**：0.20.2 的 empty Wheel 是纯 Python（`py3-none-any`），
   可以跨 Python 版本复用。0.24.0 的 empty wheel 变成 `cp312-cp312-linux_x86_64`。
   只要声明了 Rust 扩展，即使不编译任何 `.so` 文件，Wheel 也会被标记为与 CPython 版本相关。

   三个后果：Wheel 与 Python 小版本绑定，目前意味着需要 3.10、3.11、3.12 三个版本的后端。
   相同 Python 小版本的 Wheel 包是否可跨平台使用待测试给结论。
   另外 Wheel 中目前没有编译 Rust 库，意味着 `VLLM_USE_RUST_FRONTEND` 必须保持默认值 "0"。

3. **xgrammar 必须重新打包**：xgrammar 是 vLLM 的配套库。0.20.2 解析到 0.1.x，其中不带
   Torch/Triton 依赖的声明，因此不用处理。0.24.0 解析到 0.2.3，声明了对 `torch>=1.10.0`
   和 `triton` 的依赖。理论上，先安装了 Torch 和 Triton 之后，pip 安装时会检测到 Torch
   和 Triton 已经安装，不会覆盖。安全期间，也要做重新打包（repack）处理，形成
   `0.2.3+flagos` 版本（详见 [§4.1](backends/metax.md)）。

4. **构建脚本 / 配置规则微调**：之前用于 0.20.2 vLLM 的 `build-and-repack.sh` 脚本需要微调，
   构建依赖添加了 `setuptools-rust>=1.9.0` 和 `wheel` 两项；`config.yaml` 的依赖剥离规则随
   0.24.0 的依赖清单更新（新增剥离 `humming-kernels`、`quack-kernels`、`tokenspeed-mla`、
   `torch-c-dlpack-ext` 等 CUDA 内核库，清空不再依赖的 `apache-tvm-ffi`。

**待确认事项**

- **setuptools 版本问题**：Runtime 镜像中目前 `setuptools==84.0.0`，超出 vllm-plugin-FL
  的 pyproject.toml 所要求的 `<81`，可能会有问题。0.20.2 已验证 84 能构建，先保持不动。

---

## 附录 · 验证命令（容器内）

metax 形式（含 `compiler` 切换 + `VLLM_USE_FLASHINFER_SAMPLER=0`，NVIDIA 通用）：

```bash
cd /app/vllm-plugin-FL && compiler flagtree && VLLM_USE_FLASHINFER_SAMPLER=0 \
  nohup /flagos/bin/python -m vllm.entrypoints.openai.api_server \
  --model /models/Qwen3-4B --port 8031 --enforce-eager --dtype bfloat16 \
  > /tmp/serve.log 2>&1 &

curl -s localhost:8031/v1/completions -H 'Content-Type: application/json' \
  -d '{"model":"/models/Qwen3-4B","prompt":"The capital of France is","max_tokens":16,"temperature":0}'
```

NVIDIA 插件安装 —— 仅当前源安装路径需要（必须 `--no-build-isolation`，缺失工具链
从厂商 PyPI 补齐）；插件以 wheel 形式发布后（[§7](decisions.md) 合并路线），此块整体省略：

```bash
/flagos/bin/pip install --no-cache-dir wheel scikit-build-core==0.11 cmake \
  -i https://resource.flagos.net/repository/flagos-pypi-nvidia/simple/ \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple
cd /app/vllm-plugin-FL && /flagos/bin/pip install -e . --no-build-isolation
/flagos/bin/pip install vllm==0.24.0+flagos
```
