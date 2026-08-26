# vllm 0.20.2 — NVIDIA cuda12.8

> 本文对应原报告第 2 部分 §2.1。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.1 NVIDIA cuda12.8（参考实现，2026-08-23 起 empty 模式）

**日期:** 2026-07-27/28　**平台:** NVIDIA H20 (8×)

**目标:** vllm 0.20.2 + vllm-plugin-FL，`flagos-runtime-nvidia-cuda12.8:2.1.1`

NVIDIA 是首个跑通的后端，最初使用 **standard 构建**（官方预编译 wheel，含
vllm 自带 CUDA kernel）。2026-08-23 起全线统一 empty 模式，standard 构建
退役（见 [§5.3](../decisions.md)）；本记录保留的历史差异均标注"已被 §1
取代"。这些踩坑正是标准流程成型的由来（详见 [§6](../playbook.md)）。

### 环境 · numpy 版本冲突

vllm 依赖链里 `opencv-python-headless` 声明 `numpy>=2`，与当时 FlagGems 硬
锁的 `numpy==1.26.4` 冲突（14 个后端中没有任何 vendor torch 声明 `numpy<2`）。
最终确立 [§1.7](../playbook.md) 的策略：FlagGems 不 pin numpy，build-infra
按后端锁定（nvidia-cuda12.8 为 Python 3.12 → `numpy==2.3.5`）。演进全过程见
[§6](../playbook.md)。

> **事后更正（[§2.4](hygon.md)）：** 上面这个"冲突"其实是**伪冲突**——opencv
> 的 `numpy>=2` 是 faked 声明，其 wheel 编于 numpy 2.x 但运行时向后兼容 1.x
> （实测 1.26.4 下 C-API 往返完好）。当时若识破这一点，本可继续沿用全局
> `numpy==1.26.4`，无需 bump/revert。真实约束只有 py 版本上限与厂商 torch
> ABI 两条（[§1.7](../playbook.md)）。

### Repack（standard）

```bash
pip download --no-deps --dest /tmp/vllm-dl "vllm==0.20.2" \
  --index-url https://mirrors.aliyun.com/pypi/simple
python3 packaging/vllm/repack.py /tmp/vllm-dl/vllm-0.20.2-*.whl
```

> **历史差异：** 此次 repack 早于 `+flagos` 后缀方案（当时按
> [§5.1](../decisions.md) 之前的做法处理版本号）。按 [§1.3](../playbook.md)，
> 今天应统一加 `+flagos`。递归剥离在 standard 构建下发现的 torch-声明间接
> 依赖比 empty 多（standard wheel 未跳过硬件后端）。

上传（当时手动传 token；今天用 `build-and-repack.sh --upload`）：

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-nvidia/ \
  /tmp/packaging/vllm/output/vllm-0.20.2-*.whl
```

### 安装

> **历史差异（已被 [§1.4](../playbook.md) 取代）：** 此次用 `--index-url aliyun
> --extra-index-url vendor`（Aliyun 为主）。当时以为 `--extra-index-url`
> 会"优先"——**这是错的**：pip 把所有索引拉平，按版本号选最高。真正让我们的
> wheel 胜出的是 `+flagos` 版本号，与索引主次无关。今天按
> [§1.4](../playbook.md) 用 vendor 为主索引的单步安装即可。

运行时依赖锁定依据 `configs.yaml` 的 `nvidia-cuda12.8`：

```bash
pip install \
  --index-url https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple \
  torch==2.10.0+cu128 torchaudio==2.10.0+cu128 torchvision==0.25.0+cu128 \
  flagtree==0.6.0 flag_gems==5.3.2 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.1 numpy==2.3.5
```

安装 vllm-plugin-FL（NVIDIA 编译 C 扩展）：

```bash
git clone https://github.com/flagos-ai/vllm-plugin-FL
cd vllm-plugin-FL && VLLM_VENDOR=cuda pip install --no-build-isolation .
```

### 遇到的 Bug 及根因

1. **现象：** `import vllm` 失败：`ModuleNotFoundError: No module named 'regex'`

   **根因：** METADATA 在 `License-File` 删除处留空行截断，后面 82 行 `Requires-Dist`
   对 pip 不可见

   **修复：** 正则加 `\n?` 吃掉尾随换行（已纳入 [§1.3](../playbook.md)）

2. **现象：** numpy 1.26.4→2.3.5 升级，flaggems 崩溃

   **根因：** `opencv-python-headless` 声明 `numpy>=2`，flaggems 硬锁 `numpy==1.26.4`

   **修复：** FlagGems 不 pin numpy；configs.yaml 按后端锁定（[§1.7](../playbook.md)）

3. **现象：** vllm 安装后 `sqlalchemy` 消失

   **根因：** flaggems 用 `--no-deps` 装，其依赖未拉取，vllm 解析时又卸载

   **修复：** 装 flaggems 不用 `--no-deps`

4. **现象：** serve 警告 `_C.abi3.so: undefined symbol: _ZN3c10...`

   **根因：** vllm 二进制 wheel 与主机 CUDA ABI 不匹配——非致命，C 扩展优雅降级

   **修复：** PoC 可接受；生产需用匹配 CUDA 版本源码编译

### serve + 推理 —— ✅ 成功

```bash
export VLLM_PLUGINS=fl
vllm serve /models/Qwen3.6-35B-A3B --served-model-name qwen \
  --host 0.0.0.0 --port 8000 --tensor-parallel-size 2 \
  --max-model-len 32768 --trust-remote-code
```

```json
{"choices":[{"message":{"content":"Here's a thinking process:\n\n1. **Analyze User Input:**..."}}]}
{"usage":{"prompt_tokens":17,"total_tokens":145,"completion_tokens":128}}
```

### Stack 验证（nvidia-cuda12.8）

```
torch:        2.10.0+cu128  ✅  (from vendor PyPI)
torchaudio:   2.10.0+cu128  ✅
torchvision:  0.25.0+cu128  ✅
flagtree:     0.6.0         ✅  (default compiler)
flag_gems:    5.3.2         ✅  (numpy relaxed)
triton:       3.6.0         ✅  (side compiler at /opt/triton)
numpy:        2.3.5         ✅  (was 1.26.4)
vllm:         0.20.2        ✅  (repacked, from vendor PyPI)
vllm_fl:      loaded        ✅  (plugin wheel 0.2.1+g825c1cd, release-0.2;
                                 旧 standard 期 source build VLLM_VENDOR=cuda 已退役 §5.3)
CUDA:         True          ✅
Inference:    Qwen3.6-35B-A3B ✅  (prompt=17 / completion=128 tokens)
```

### 2026-08-23 复核（empty 模式 + app 镜像 E2E）

[§5.3](../decisions.md) 决策后 NVIDIA 并入 empty 模式。plugin wheel 改从
**release-0.2** 分支构建（v0.2.1 = `825c1cd`，见 [§1.5](../playbook.md)）：
产物 `vllm_plugin_fl-0.2.1+g825c1cd-py3-none-any.whl`（sha256
`783861f5…d673c`），随 app 镜像单步安装。

**App 镜像构建 + 验证（✅，push 2026-08-23 10:57 UTC）：**

- 镜像：`harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda12.8:2.1.2-0.2.1_g825c1cd`
  （digest `bce4e3c7…`；tag 中 `0.2.1_g825c1cd` = plugin `0.2.1+g825c1cd`）
- 底层 runtime：`flagos-runtime-nvidia-cuda12.8:2.1.2`（empty 模式单步安装
  `vllm==0.20.2+flagos` + `vllm-plugin-fl==0.2.1+g825c1cd`）
- 构建后验证全过：Matrix unchanged（torch/flagtree/flag_gems 未被覆盖）、
  `vllm + vllm_fl import OK`、App-image verification PASSED。

**h20 节点 E2E —— 双编译器路径各跑一遍（empty 模式，同一 app 镜像）：**

> 空模式镜像与 2026-08-16 双编译器验证用的 vendor（standard）镜像不是同一
> 镜像，旧记录不能背书 empty 产物。empty 模式下两条编译器路径分别实测：

**F 路径（flagtree，默认编译器）—— ✅**

```bash
docker run -d --gpus all \
  -v /data/tqm/models:/data/models:ro --network host \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda12.8:2.1.2-0.2.1_g825c1cd
```

- 默认 CMD（`vllm-serve` source `/etc/bash_env.sh` 后 exec，不切换编译器，
  默认 flagtree active）即 F 路径；约 60 s 就绪（`Application startup
  complete`）；日志确认 plugin fl 激活（Platform plugin fl is activated，
  注册 DeepseekV4ForCausalLM / DeepSeekV4MTPModel override），
  `VLLM_PLUGINS=fl` 已内置镜像 env。
- `curl /v1/completions` 输出连贯：`The capital of France is Paris. The
  capital of Germany is Berlin...`（prompt 5 / completion 32 token）。吞吐：
  Avg prompt 0.5 tok/s，Avg generation 3.2 tok/s。

**T 路径（triton 3.6.0 side compiler）—— ✅（2026-08-23 补验）**

```bash
docker run -d --gpus all \
  -e PYTHONPATH=/opt/triton \
  -v /data/tqm/models:/data/models:ro --network host \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda12.8:2.1.2-0.2.1_g825c1cd
```

- `-e PYTHONPATH=/opt/triton` 显式切到 triton（`docker exec … compiler` 确认
  `active compiler: triton - 3.6.0`），其余参数同默认 CMD。
- 约 35 s 就绪（`Application startup complete`）；同一 prompt 输出连贯：
  `Paris. The capital of Germany is Berlin. The capital of Italy is Rome.`…
  （prompt 5 / completion 32 token）。吞吐与 F 路径一致：Avg prompt 0.5
  tok/s，Avg generation 3.2 tok/s。
- 两容器验证后均已清理。启动文档已发布（launch_docs + image_tag，见
  `status_matrix.vllm0.20.2.yaml`）。

**nvidia-cuda13.3（2026-08-23 补验，待办 #1 闭环）**

- App 镜像：`harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda13.3:2.1.2-0.2.1_g825c1cd`
  （digest `6f65605893aa…`；tag `0.2.1_g825c1cd` = plugin `0.2.1+g825c1cd`）
- 底层 runtime：`flagos-runtime-nvidia-cuda13.3:2.1.2`（cuda13.3 栈：Python 3.12、
  torch 2.11.0+cu130、triton 3.6.0、flagtree 0.6.1、flaggems 5.3.4）
- 构建后验证全过：Matrix unchanged（torch/flagtree/flag_gems 未被覆盖）+
  `vllm + vllm_fl import OK`。镜像已 push。
- 双编译器路径各跑一遍（empty 模式，同一 app 镜像），F/T 均 ✅：

**F 路径（flagtree 默认）—— ✅**

```bash
docker run -d --gpus all \
  -v /data/tqm/models:/data/models:ro --network host \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda13.3:2.1.2-0.2.1_g825c1cd
```

- 默认 CMD 即 F 路径（flagtree 默认 active）；约 30 s 就绪；plugin fl 激活。
- `curl /v1/completions` 输出连贯：`Paris. The capital of Paris is...? ...`
  （prompt 5 / completion 32 token）。

**T 路径（triton 3.6.0 side compiler）—— ✅**

```bash
docker run -d --gpus all \
  -e PYTHONPATH=/opt/triton \
  -v /data/tqm/models:/data/models:ro --network host \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda13.3:2.1.2-0.2.1_g825c1cd
```

- `-e PYTHONPATH=/opt/triton` 显式切到 triton（`compiler` 确认 active =
  triton 3.6.0）；约 30 s 就绪；同一 prompt 输出连贯。两容器验证后均已清理。

### 待办

1. ~~扩展到 nvidia-cuda13.3（相同模式，torch 2.11.0+cu130）~~ —— ✅ 2026-08-23
   （见上文 cuda13.3 复核记录）。
1. ~~empty-mode 性能基准~~ —— [§5.3](../decisions.md) 已定案全线统一 empty
   （2026-08-23），基准不再门控；empty 下 NVIDIA 性能实证见
   [0.24.0 报告](../../vllm-0.24.0/index.md)（Qwen3-4B E2E）。
1. NVIDIA empty 模式 app 镜像 E2E —— ✅ 2026-08-23（见上文复核记录）。
