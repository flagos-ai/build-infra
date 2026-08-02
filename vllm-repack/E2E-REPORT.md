# vllm-repack — 端到端验证报告

## 0. 背景

vLLM 原生 wheel 包中包含对 Torch、Triton 等关键软件包的声明式依赖。
如果不作处理，把 vllm 安装到 FlagOS runtime 环境时，
会覆盖现有环境中精心匹配、反复验证过的版本矩阵——
例如带入非厂商支持的 Torch 或 Triton 版本。
vLLM 所声明的其他间接依赖包中也存在同类问题（实际验证过程中已证实）。

因此，需要对 vLLM 及其声明依赖中"危险的"软件包进行预处理，或称重新打包
（repack），去除会破坏环境的依赖声明。重新打包后的 vLLM（及所牵涉的其他
Wheel）上传到 resource.flagos.net 的 Vendor PyPI 服务器，供流程化验证使用。

本文档分两部分：

- **第 1 部分（标准流程）** 是面向"新后端"的推荐端到端做法（playbook）。
  它以 mthreads 后端跑通的路径为基准——`empty` 构建 + `+flagos` 版本后缀 +
  单步安装——这是目前验证最充分、最省事的方案。**除 NVIDIA 外**的所有后端
  都应照此执行。
- **第 2 部分（后端验证记录）** 是三个已完成后端的实测记录，作为标准流程的
  worked example。其中 NVIDIA 是首个跑通、也是唯一使用标准构建的后端；
  MetaX 是首个 `empty` 后端；mthreads 是标准流程的范例来源。个别后端因历史
  原因走过弯路，记录中已标注哪些步骤已被标准流程取代。

> **术语：`+flagos`** —— repack 后为 wheel 版本号追加的 PEP 440 本地版本
> 后缀（如 `0.20.2` → `0.20.2+flagos`）。它是"这个 wheel 出自 FlagOS repack
> 流程"的显式标记，也是单步安装能稳定命中我们的包的关键（见 §1.4、§5.1）。

---

# 第 1 部分 · 标准流程（Playbook）

## 1.1 设计原则与约束

1. **PyPI 分离** —— Vendor PyPI 只放 repacked wheel，其余安全依赖从公网
   （Aliyun 镜像）拉取。不托管无须处理的间接依赖，维护成本太高。
1. **保留 deps，不用 `--no-deps`** —— repacked wheel 保留除剥离项以外的
   所有 `Requires-Dist`，让 pip 正常解析安全依赖。
1. **国内节点走 Aliyun** —— 通常无法访问 pypi.org，所有额外依赖从
   `mirrors.aliyun.com` 下载。
1. **统一 `+flagos` 后缀** —— 所有 repacked wheel（主包 + 递归发现的间接
   依赖）统一加 `+flagos` 本地版本后缀，**保持原始 platform tag**
   （`py3-none-any`），不伪造 ABI（不改 WHEEL Tag）。PEP 440 下
   `0.20.2+flagos > 0.20.2`，pip 会优先选中我们的 wheel——无需两步安装，
   也无需伪造平台标签。

## 1.2 构建模式

| 模式 | 适用后端 | 说明 |
|---|---|---|
| **empty** | 除 NVIDIA 外的所有后端 | `VLLM_TARGET_DEVICE=empty` 从源码编译不含硬件 kernel 的 vllm；硬件算子由 vllm-plugin-FL + flag_gems 提供。产物为 `py3-none-any`，纯 Python。 |
| **standard** | 仅 NVIDIA | `pip download` 官方预编译 wheel，含 vllm 自带 CUDA kernel（`_C`）。 |

> NVIDIA 是否也统一到 `empty` 模式尚未决定，取决于性能基准测试结果，
> 见 §5.3。在此之前 NVIDIA 维持 standard 构建。

## 1.3 Repack

使用 `vllm-repack/repack.py`（分类规则见 `vllm-repack/config.yaml`）处理 wheel：

1. **加 `+flagos` 版本后缀** —— 主包与所有递归发现的间接依赖统一处理。
   保持原始 platform tag，不改 WHEEL Tag。
1. **Metadata-Version 从 2.4 降级为 2.2** —— 方便 Nexus 解析。
1. **METADATA 正则替换不留空行** —— 对 `License-File`、`Dynamic:` 行的删除
   必须吃掉尾随换行（正则加 `\n?`）；否则 header 在空行处被截断，后面所有
   `Requires-Dist` 对 pip 不可见（曾导致 `ModuleNotFoundError`，见 §2.1）。
1. **递归剥离间接依赖** —— `repack_recursive()` 在 repack 时解析 pip 的
   实际依赖树，下载每个保留的依赖，检查其 METADATA，对声明了 torch/triton
   家族的包（规则见 `config.yaml` 的 `strip_from_indirect`）自动剥离并同样
   打上 `+flagos`。**不再维护手工 `also_repack` 列表**——树是动态发现的，
   具体哪些间接依赖需要处理取决于构建模式（empty 构建跳过了硬件后端，
   声明 torch/triton 的间接依赖比 standard 构建少）。

顶层剥离规则（`config.yaml`）：`remove_torch_chain`（torch/torchaudio/
torchvision/torchcodec）、`remove_cuda_only`（PyNvVideoCodec、nvidia-* 等）、
`remove_orphaned`（随上游一起失去消费者的包，如 apache-tvm-ffi）。

## 1.4 安装与验证流程

`+flagos` 后缀让安装收敛为**单步**（vendor 为主索引，Aliyun 补充安全依赖）：

```bash
VENDOR=https://resource.flagos.net/repository/flagos-pypi-<vendor>/simple
ALIYUN=https://mirrors.aliyun.com/pypi/simple

# 1. 运行时依赖 —— 版本锁定依据 configs.yaml 的对应后端
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" \
  <torch/torchvision/... 见 configs.yaml deps> flag_gems==<configs.yaml flaggems> \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.1 numpy==<per-backend, 见 §1.7>

# 2. repacked vllm —— 单步即可，无需 --no-deps
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" vllm==0.20.2+flagos
```

> **显式 pin `+flagos`。** 建议直接写 `vllm==0.20.2+flagos` 而非裸
> `vllm==0.20.2`：后者依赖 pip 在候选中偏好更高的本地版本（即
> `0.20.2+flagos` 排在 `0.20.2` 之上）才能命中我们的包——这一偏好虽符合
> PEP 440，但跨后端尚未全部实测（§5.1）。显式带 `+flagos` 则无歧义，
> 直接锁定 repacked wheel。

> **为什么单步就够（曾经需要两步）？** repack 若只剥掉 vllm 自身的 torch
> 声明、却漏掉间接依赖（如 xgrammar、compressed-tensors）的 torch 声明，
> pip 仍会从 Aliyun 拉一个更高的 base 版本 torch → 覆盖 vendor 的本地版本
> torch。早期 MetaX 因此被迫用 `--no-deps` 两步锚定（见 §2.2）。
> **PR #280** 让 repack **递归**把所有间接依赖 pin 到 `+flagos` 后，torch
> 约束不再泄漏，单步安装即安全——已在 mthreads 上实测（131 包依赖树零
> torch/triton/nvidia 泄漏，见 §2.3）。

验证步骤：

1. 选择待验证后端，确认 FlagOS runtime 镜像为最新（含可用的 Torch、
   Triton/FlagTree、FlagGems 组合）。
1. 目标机上以 `-d` 启动测试容器（带硬件访问），`docker exec` 进入。
1. 装运行时依赖，安装 repacked vllm（上文单步）。
1. 检查 vllm 安装成功。
1. 检查 Torch、Triton/FlagTree 等核心包版本未被覆盖（vendor 本地版本后缀
   仍在，如 `+musaX.Y.Z`、`+metaxX.Y.Z`、`+cuXXX`）。
1. 克隆并安装 `vllm-plugin-FL`（见 §1.5）。
1. 检查 `vllm serve` 可启动，处理各类启动问题。
1. 检查推理成功。

验证过程中随时记录新发现。

## 1.5 vllm-plugin-FL

vllm-plugin-FL 定位为上游 vllm 的插件，目标是适配不同模型、不同后端；
具体适配可能涉及算子层选择甚至针对后端的定制。

- **empty 模式后端**：**纯 Python 安装，不设 `VLLM_VENDOR`**：
  `pip install --no-build-isolation -e .`。硬件算子由 plugin 的 dispatch
  机制路由到 flag_gems（Triton）。
- **NVIDIA（standard）**：`VLLM_VENDOR=cuda pip install --no-build-isolation .`
  编译 C 扩展。

发现 plugin bug 时向其 GIT 仓库提 PR，**尽量不打破** plugin 现有的模型层 /
算子层适配机制，以最小改动打通。

## 1.6 FlagGems

验证过程**不使用** FlagGems GIT 仓库 master head：既避免不必要的源码克隆，
也保证使用确定的版本。从各 Vendor PyPI 下载 FlagGems Python wheel，版本与
FlagOS runtime 镜像锁定一致——记录于 `configs.yaml` 全局属性 `flaggems`
（当前 `5.3.2`）。

发现 FlagGems bug 时先提 PR；合并后用**新的** GIT Tag 重新打包、重新上传
（流程走 build-infra 的 `flaggems-release.yml`）。

> **注意（历史教训）：** 曾经出现过删除 `v5.3.2` 再用同名 `v5.3.2` 重打的
> 操作（见 §6）。改写已发布的 tag 会破坏可复现性，应避免——bug 修复一律用
> 递增的新 tag。

## 1.7 numpy 版本

numpy **按后端在 `configs.yaml` 显式锁定**，不由 FlagGems 硬锁：

- Python 3.12 后端（如 nvidia-cuda12.8/13.3、ascend）：`numpy==2.3.5`
- Python 3.10 后端（如 mthreads、cambricon）：`numpy==2.2.6`
  （Python 3.10 不支持 `numpy>2.2.6`）

FlagGems 侧**不 pin** numpy（`pyproject.toml` 用不锁定的 `numpy`），把版本
决定权交给 build-infra 的 per-backend 锁定。因此不同后端 numpy 版本不同是
**预期行为**，不是不一致。（这一策略的由来见 §6 的 numpy 演进。）

## 1.8 工具链

**已有：**

| 文件 | 用途 |
|------|------|
| `vllm-repack/repack.py` | repack 工具：`+flagos` 后缀、Metadata 降级、递归剥离间接依赖 |
| `vllm-repack/config.yaml` | repack 分类规则（`remove_*` / `strip_from_indirect`） |
| `vllm-repack/build-and-repack.sh` | 构建（empty/standard）→ repack → `--upload` twine 上传到 vendor PyPI |
| `vllm-repack/verify-vllm-backend.sh` | 在目标机安装 repacked vllm + plugin，验证 serve/推理 |

**待建（⬜）：**

| 文件 | 用途 |
|------|------|
| `app/vllm/Containerfile` | `FROM runtime` → pip install vllm + vllm-plugin-FL |
| `.github/workflows/vllm-app.yml` | 完整 CI：repack → upload → build → verify → push |

---

# 第 2 部分 · 后端验证记录（worked examples）

三个后端按第 1 部分的模板组织：**环境 → repack → 安装 → 阻塞点 → Stack
验证 → 待办**。标准流程（§1）即从这些记录中提炼；记录里保留了个别后端走过
的弯路，并标注哪些已被 §1 取代。

## 2.1 NVIDIA cuda12.8（参考实现 / 唯一 standard 构建）

**日期:** 2026-07-27/28　**平台:** NVIDIA H20 (8×)
**目标:** vllm 0.20.2 + vllm-plugin-FL，`flagos-runtime-nvidia-cuda12.8:2.1.1`

NVIDIA 是首个跑通的后端，也是唯一使用 **standard 构建**（官方预编译 wheel，
含 vllm 自带 CUDA kernel）的后端。它早于 `+flagos` / 单步安装的确立，下面
记录中标注了已被 §1 取代的步骤。这些踩坑正是标准流程成型的由来（详见 §6）。

### 环境 · numpy 版本冲突

vllm 依赖链里 `opencv-python-headless` 声明 `numpy>=2`，与当时 FlagGems 硬
锁的 `numpy==1.26.4` 冲突（14 个后端中没有任何 vendor torch 声明 `numpy<2`）。
最终确立 §1.7 的策略：FlagGems 不 pin numpy，build-infra 按后端锁定
（nvidia-cuda12.8 为 Python 3.12 → `numpy==2.3.5`）。演进全过程见 §6。

### Repack（standard）

```bash
pip download --no-deps --dest /tmp/vllm-dl "vllm==0.20.2" \
  --index-url https://mirrors.aliyun.com/pypi/simple
python3 vllm-repack/repack.py /tmp/vllm-dl/vllm-0.20.2-*.whl
```

> **历史差异：** 此次 repack 早于 `+flagos` 后缀方案（当时按 §5.1 之前的
> 做法处理版本号）。按 §1.3，今天应统一加 `+flagos`。递归剥离在
> standard 构建下发现的 torch-声明间接依赖比 empty 多（standard wheel 未
> 跳过硬件后端）。

上传（当时手动传 token；今天用 `build-and-repack.sh --upload`）：

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-nvidia/ \
  /tmp/vllm-repack/output/vllm-0.20.2-*.whl
```

### 安装

> **历史差异（已被 §1.4 取代）：** 此次用 `--index-url aliyun
> --extra-index-url vendor`（Aliyun 为主）。当时以为 `--extra-index-url`
> 会"优先"——**这是错的**：pip 把所有索引拉平，按版本号选最高。真正让我们的
> wheel 胜出的是 `+flagos` 版本号，与索引主次无关。今天按 §1.4 用 vendor
> 为主索引的单步安装即可。

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

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | `import vllm` 失败：`ModuleNotFoundError: No module named 'regex'` | METADATA 在 `License-File` 删除处留空行截断，后面 82 行 `Requires-Dist` 对 pip 不可见 | 正则加 `\n?` 吃掉尾随换行（已纳入 §1.3） |
| 2 | numpy 1.26.4→2.3.5 升级，flaggems 崩溃 | `opencv-python-headless` 声明 `numpy>=2`，flaggems 硬锁 `numpy==1.26.4` | FlagGems 不 pin numpy；configs.yaml 按后端锁定（§1.7） |
| 3 | vllm 安装后 `sqlalchemy` 消失 | flaggems 用 `--no-deps` 装，其依赖未拉取，vllm 解析时又卸载 | 装 flaggems 不用 `--no-deps` |
| 4 | serve 警告 `_C.abi3.so: undefined symbol: _ZN3c10...` | vllm 二进制 wheel 与主机 CUDA ABI 不匹配——非致命，C 扩展优雅降级 | PoC 可接受；生产需用匹配 CUDA 版本源码编译 |

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
vllm_fl:      loaded        ✅  (source build, VLLM_VENDOR=cuda)
CUDA:         True          ✅
Inference:    Qwen3.6-35B-A3B ✅  (prompt=17 / completion=128 tokens)
```

### 待办

1. 扩展到 nvidia-cuda13.3（相同模式，torch 2.11.0+cu130）。
1. **empty-mode 性能基准**（§5.3 的决策前置）——对比 standard vs empty 的
   NVIDIA 推理性能，决定是否全线统一 empty。

## 2.2 MetaX maca3.7.2.1（首个 empty 后端）

**日期:** 2026-07-28/31　**平台:** MetaX C550 (8×, 64GB)
**节点:** metax124　**MACA:** 3.7.2.0, Driver 3.8.30
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-metax-maca3.7.2.1:2.1.1`

首个 `empty` 构建后端。MetaX MACA 无 CUDA 扩展，走 `VLLM_TARGET_DEVICE=empty`
——编译不含硬件 kernel 的 vllm，硬件算子由 vllm-plugin-FL 的 metax vendor
backend + flag_gems 提供。repack 规则、间接依赖处理、plugin 安装与 §1 一致。

> **状态：端到端已完成 ✅**（2026-07-31）。在设备可见的 `vllm-serve-metax`
> 容器里，`vllm serve Qwen3-4B`（TP=1, `--enforce-eager`, gpu-util 0.6）成功
> 启动并返回正确推理。

### Repack（empty）

```bash
cd /workspace/vllm
VLLM_TARGET_DEVICE=empty MAX_JOBS=64 \
  pip wheel --no-build-isolation --no-deps -w /tmp/empty .
# → vllm-0.20.2+empty-...whl（无 .so）
python3 vllm-repack/repack.py /tmp/empty/vllm-0.20.2+empty-*.whl
```

empty 构建跳过了硬件后端，empty vllm 的 77 个间接依赖中只有 **2 个**在自身
METADATA 声明了 torch/triton（对比 §2.1 standard 构建更多）：

| 包 | 声明 |
|---|---|
| `compressed-tensors`==0.15.0.1 | `torch>=1.7.0` |
| `xgrammar`==0.2.3 | `torch>=1.10.0` + `triton` |

`repack_recursive()` 自动发现并逐一剥离、上传（§1.3）。其他间接依赖
（transformers、safetensors、outlines_core…）仅在未激活的 extras 中声明
torch，pip 不激活 extras，无需处理。

> **历史差异（已被 §1.3 取代）：** 早期 MetaX repack 为绕过 pip 平台匹配，
> 做过两件已废弃的临时操作——(a) 去掉 `+empty` 后缀改回裸 `0.20.2`；
> (b) 把 WHEEL Tag 从 `py3-none-any` **伪造**成
> `cp38-abi3-manylinux_2_35_x86_64`。§5.1 已否定伪造 platform tag（声明
> 不存在的 ABI，误导），标准做法是加 `+flagos` 并保留 `py3-none-any`。

### 安装

> **历史差异（已被 §1.4 取代）：** 因为当时 repack 未把间接依赖 pin 到
> `+flagos`，`torch-2.8.0+metax3.7.2.0` 在 PEP 440 里排序低于 Aliyun 的
> `torch-2.11.0`，一步安装会触发 torch 降级，只能两步 `--no-deps` 锚定：
> ```bash
> pip install --no-deps --index-url "$VENDOR" vllm==0.20.2   # 锁 repacked
> pip install         --index-url "$ALIYUN" vllm==0.20.2     # 补 safe deps
> ```
> PR #280（递归 `+flagos` pin）之后此坑消失，单步即可（§1.4）。mthreads
> 已实测验证单步安全（§2.3）。

运行时依赖（vendor 为主）：

```bash
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" \
  torch==2.8.0+metax3.7.2.0 torchaudio==2.4.1+metax3.7.2.0 \
  torchvision==0.15.1+metax3.7.2.0 flash_attn==2.6.3+metax3.7.2.0torch2.8 \
  flagtree==3.1.0+metax3.7.2.0 triton==3.0.0+metax3.7.2.0 flag_gems==5.3.2 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.3 numpy==2.3.5
```

安装 vllm-plugin-FL —— 纯 Python，不设 `VLLM_VENDOR`（§1.5）：

```bash
cd /workspace/vllm-plugin-FL && pip install --no-build-isolation -e .
```

### 阻塞点：`reshape_and_cache_flash` 算子（由 plugin-FL #333 修复）

empty wheel 不含编译的 `_C_cache_ops` C kernel。MetaX flash attn 后端在
`fa_utils.py` 把 `reshape_and_cache_flash` 直接绑定到
`vllm._custom_ops.*` → `torch.ops._C_cache_ops.*`，首次前向崩溃：

```none
AttributeError: '_OpNamespace' '_C_cache_ops' object has no attribute
'reshape_and_cache_flash'
```

早期尝试 #319（`_C_cache_ops` Triton fallback）**从未生效**——守卫
`hasattr(torch.ops, "_C_cache_ops")` 对惰性 `_OpNamespace` 恒真，且 metax
C550 已禁用 Triton。

**修复（[#333](https://github.com/flagos-ai/vllm-plugin-FL/pull/333)）：**
把 `reshape_and_cache_flash` 注册为一等 dispatch op：

- `flaggems/flaggems.py` — 新增 `FlagGemsBackend.reshape_and_cache_flash`，
  转发到纯 Triton 的 `flag_gems.fused.reshape_and_cache_flash`。
- `flaggems/register_ops.py` — 注册为 `default.flagos`（`_has_flaggems_op` 守卫）。
- `metax/impl/attention/utils/fa_utils.py` — 调用点改为
  `CachedOp("reshape_and_cache_flash")`，不再绑定 vllm 私有 C op。

留在 dispatch 抽象内（policy 驱动、可回退、厂商无关），不耦合 vllm 私有
`_C_cache_ops` ABI。#333 取代 #319（已关闭）。

### serve + 推理 —— ✅ 成功

```bash
export VLLM_FL_DISPATCH_DEBUG=1        # 打印 dispatch 选择，确认 default.flagos
vllm serve /data/models/Qwen/Qwen3-4B --port 8031 \
  --gpu-memory-utilization 0.6 --enforce-eager \
  --trust-remote-code --max-model-len 2048
# NCCL→MCCL 由 pynccl_wrapper patch 自动完成，无需额外 env
```

```json
{"choices":[{"text":" Paris. The capital of Germany is Berlin. The capital of Italy is Rome.",
  "finish_reason":"length"}],
 "usage":{"prompt_tokens":5,"completion_tokens":16,"total_tokens":21}}
```

前向日志确认算子走对路（无 `_C_cache_ops` / `_C.silu_and_mul` 报错）：

```
Op 'silu_and_mul' using 'default.flagos' (kind=flagos, vendor=None)
Op 'reshape_and_cache_flash' using 'default.flagos' (kind=flagos, vendor=None)
```

> **实测注意事项：**
> - MCCL communicator 冷启动很慢（~11 min，进程 15–25% CPU，看似 hang 实为
>   在跑），不要过早 kill。
> - 被 kill 的 engine 以 `VLLM::EngineCore` 残留（`pkill -f "vllm serve"`
>   匹配不到）占显存，导致下次误报 "Free memory < desired"——按 PID 或
>   `pkill -9 -f EngineCore` 清理。

### Stack 验证

```
torch:        2.8.0+metax3.7.2.0    ✅  from vendor PyPI (未降级)
torchaudio:   2.4.1+metax3.7.2.0    ✅
torchvision:  0.15.1+metax3.7.2.0   ✅
flash_attn:   2.6.3+metax3.7.2.0    ✅
flagtree:     3.1.0+metax3.7.2.0    ✅  默认编译器
triton:       3.0.0+metax3.7.2.0    ✅
flag_gems:    5.3.2                 ✅
vllm:         0.20.2                ✅  empty, repacked, vendor PyPI
vllm_fl:      installed             ✅  纯 Python + #333
MACA device:  ✅ 可见                mx-smi (C550 8×64GB)
vllm serve:   ✅ 启动成功            TP=1, enforce-eager, gpu-util 0.6
Inference:    ✅ 成功                Qwen3-4B, prompt=5 / completion=16
```

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| plugin-FL #333 | ✅ 已提，E2E 通过 | `reshape_and_cache_flash`→flag_gems（`CachedOp`） |
| plugin-FL #319 | ✅ 已关闭 | 守卫恒真从不生效，被 #333 取代 |
| plugin-FL #325（`_maca`→F.silu/F.gelu）| ✅ 已关闭 | empty wheel 上 dispatch 不走 vendor 路径，实测不需要（仅 +cpu wheel 有意义） |
| repack.py empty 支持 + 递归审计 | ✅ | PR #244 #247 |
| 更大模型 / graph / TP>1 | ⬜ | 仅测过 Qwen3-4B + eager |
| FlagGems pyproject build-system.requires 加 `wheel==0.45.0` | ⬜ | |

## 2.3 mthreads-musa5.2.0（标准流程范例）

**日期:** 2026-08-01/02　**平台:** MTT S5000 (8×, 80GB)
**节点:** `mthreads`（JumpServer 别名）　**MUSA:** 5.2.0-server, torch_musa 5.2.0
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-mthreads-musa5.2.0:2.1.1`

**这是第 1 部分标准流程的范例来源**——empty 构建、`+flagos` 后缀、单步安装
全部按 §1 执行且无历史包袱。与 MetaX 同为 empty 后端；唯一特殊点：mthreads
的 `torch.device.type` 是 `"musa"`（flag_gems `device_name` 也是 `"musa"`，
所有 GPU 后端中唯一非 `"cuda"` 的），这引出下面的 mul 门控阻塞。

### Repack & Upload —— ✅ 已完成（2026-08-01）

```bash
./vllm-repack/build-and-repack.sh mthreads-musa5.2.0 --upload
```

一条命令完成：empty 构建 → repack（`+flagos`）→ twine 上传到
`flagos-pypi-mthreads`。上传的包：

| 包 | 版本 | 说明 |
|------|------|------|
| vllm | 0.20.2+flagos | 主包，empty build |
| xgrammar | 0.2.5+flagos | 间接依赖，剥 torch/triton |
| compressed-tensors | 0.15.0.1+flagos | 间接依赖，剥 torch |

关键：`+flagos` 后缀（主包 + 所有递归发现的间接依赖）、A→B→C 依赖链全部
pin 到 `+flagos`（PR #280）。

> **xgrammar 版本说明：** 此处解析到 `0.2.5`，MetaX 记录（§2.2）当时是
> `0.2.3`——两次验证时间不同、上游版本推进所致。同一 vllm 0.20.2 今天重跑
> 应解析到一致版本；`repack_recursive()` 按 repack 时的实际依赖树动态决定，
> 不硬编码版本。

### 安装与验证 —— ✅ 已完成（2026-08-02）

按 §1.4 单步安装（`--index-url vendor --extra-index-url aliyun`，
`vllm==0.20.2+flagos`，**不用** `--no-deps`）。131 包依赖树中**零**
torch/triton/nvidia 泄漏：

- `torch` 保持 `2.9.1+musa5.2.0`（未降级），`triton` 不存在
- `flag_gems` 5.3.2 / `flagtree` 0.6.0+mthreads3.6 / `numpy` 2.2.6 全部完好
- `xgrammar`、`compressed-tensors` 解析到各自 `+flagos` 变体
- `vllm-plugin-FL` 安装成功（`0.0.0+gd1327ae0a`，纯 Python，不设
  `VLLM_VENDOR`），`fl` 插件正常激活

**这一结果实证了 §1.4 的单步安装** —— MetaX 曾被迫的两步 `--no-deps` 在
`+flagos` 递归 pin 后不再需要。

> **transformers 不是泄漏源** —— 其 torch 引用全在未激活的 extras
> (`[torch]`/`[all]`/`[dev]`) 之后。早前"transformers 拉 torch"的判断实为
> 未 pin 的 xgrammar bug（PR #280 已修）。

### 阻塞点：flag_gems mul 设备门控回归（由 FlagGems #5130 修复）

`vllm serve` 在模型加载阶段崩溃，命中 rope 的 `1.0 / freqs` 路径：

```none
rope: inv_freq = 1.0 / (base**...)  → Tensor.__rdiv__: reciprocal() * 1.0
 → flag_gems/ops/mul.py  mul_broadcast_func
 → torch.ops.aten.mul.Tensor.redispatch(_FALLBACK_KEYSET, a, 1.0)
RuntimeError: aten::mul.Tensor expected Tensor for 'other', found float 1.0
```

**根因——两步上游回归，并非 kernel bug。** Triton mul kernel 在 MUSA 上
所有路径均正确（实测 scalar/tensor/broadcast/fp16/bf16/int/out=/mul_/complex
误差全为 0）。崩溃纯来自设备门控：

| # | 现象 | 根因 |
|---|------|------|
| 1 | 所有 mul 在 MUSA 走 fallback，不走优化 Triton 路径 | [#4666](https://github.com/flagos-ai/FlagGems/pull/4666) 用 `device.type != "cuda"` 门控。MetaX 的 torch fork 报 `"cuda"` 故通过；mthreads 报 `"musa"`（唯一非 "cuda" GPU 后端）被挤出 |
| 2 | fallback 对标量崩溃 | [#4999](https://github.com/flagos-ai/FlagGems/pull/4999) 把 fallback 从 `torch.mul(a,b)`（可处理标量）改成 `aten.mul.Tensor.redispatch(...)`，而 `mul.Tensor` 要求 `other` 是 Tensor，标量 `1.0` 无法转换 |

**修复（[#5130](https://github.com/flagos-ai/FlagGems/pull/5130)）：** 门控从
硬编码 `"cuda"` 改为按激活后端设备名判断（符合库自身惯例，如
`_upsample_bilinear2d_aa.py` 用 `input.device.type == device.name`）：

```python
from flag_gems.runtime import device as runtime_device
_DEVICE_NAME = runtime_device.name        # "cuda" / "musa" / ...
...
if device.type != _DEVICE_NAME:           # was: != "cuda"
```

`device_name` 为 `"cuda"` 的后端（nvidia、metax、iluvatar、hygon…）不受
影响；mthreads（`"musa"`）自此走与其他后端相同的优化 Triton 路径。

> **对照 MetaX：** MetaX 没命中此坑，正因其 torch fork 报
> `device.type == "cuda"` 恰好通过门控；mthreads 是唯一暴露该回归的后端。

### serve + 推理 —— ✅ 成功

选 **DeepSeek-R1-0528-Qwen3-8B-FlagOS**（`rope_scaling.rope_type == yarn`）——
正是最直接触发上述崩溃的路径，验证修复最有说服力：

```bash
export MTHREADS_VISIBLE_DEVICES=all
vllm serve /data/DeepSeek-R1-0528-Qwen3-8B-FlagOS --port 8031 \
  --trust-remote-code --max-model-len 4096 --enforce-eager \
  --gpu-memory-utilization 0.85 --tensor-parallel-size 1
# NCCL→MCCL 由 pynccl_wrapper patch 自动完成
```

serve 到达 `Application startup complete`（device_config=musa，MCCL 后端），
全程无 `expected Tensor for 'other'` 报错。

```json
{"choices":[{"text":" a city in the north of France. It is famous for the Eiffel Tower, the Arc de Triomphe",
  "finish_reason":"length"}],
 "usage":{"prompt_tokens":6,"completion_tokens":24,"total_tokens":30}}
```

✅ 修复单独一处即打通整条 serve 路径，本模型无需其他 flag_gems / plugin 改动。

### Stack 验证

```
torch:        2.9.1+musa5.2.0     ✅  from vendor PyPI（未降级）
triton:       (absent)            ✅  MUSA 无 triton，由 flagtree 提供
flagtree:     0.6.0+mthreads3.6   ✅
flag_gems:    5.3.2 + #5130       ✅  mul 门控修复
numpy:        2.2.6               ✅  (Python 3.10)
vllm:         0.20.2+flagos       ✅  empty, repacked, vendor PyPI
vllm_fl:      0.0.0+gd1327ae0a    ✅  纯 Python（无 VLLM_VENDOR）
MUSA device:  ✅ 8× 可见           mthreads-gmi (MTT S5000 8×80GB)
vllm serve:   ✅ 启动成功          TP=1, enforce-eager, gpu-util 0.85
Inference:    ✅ 成功              DeepSeek-R1-0528-Qwen3-8B (yarn), 6→24 tokens
```

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| FlagGems mul 门控 #5130 | ✅ 已提，E2E 通过 | 门控改判 `runtime.device.name`；merge 后随 flag_gems release 打包进新镜像 |
| repack & upload (+flagos) | ✅ 已完成 | vllm / xgrammar / compressed-tensors |
| 更大模型 / TP>1 / graph | ⬜ | 仅测过 DeepSeek-8B + eager + TP=1 |
| 非 yarn 模型覆盖 | ⬜ | 可选，验证更广 rope 路径 |

**相关提交：** `main` 478de6b（repack）、PR #280（递归 `+flagos` pin）；
FlagGems [#5130](https://github.com/flagos-ai/FlagGems/pull/5130)（mul 门控）

---

# 第 3 部分 · 流程总结与决策

## 3. 自动化边界

### 3.1 可自动化

| 任务 | 方式 | 状态 |
|------|------|------|
| 构建 + repack | `build-and-repack.sh <vendor>-<backend>`（empty/standard 自动分流） | ✅ |
| 运行 repack.py | 确定性脚本，输入：wheel + config.yaml | ✅ |
| 递归发现 + 剥离间接依赖 | `repack_recursive()` 解析实际依赖树，自动 repack 声明 torch/triton 的间接依赖 | ✅ |
| 上传到 vendor PyPI | `build-and-repack.sh --upload`（twine + token） | ✅ |
| 安装 + serve 验证 | `verify-vllm-backend.sh <vendor>-<backend>` | ✅ |
| 验证 METADATA（无空行、deps 正确） | `wc -l`、`grep Requires-Dist`、removed vs retained 计数 | ⚒️ 需要脚本 |
| 一次构建上传到全部 vendor PyPI | 遍历 configs.yaml 各厂商（依赖 §5.2 empty 通用性成立） | ⚒️ 需要脚本 |
| CI：repack → upload → build → push | 模式已存在于 `flaggems-release.yml` + `runtime.yml` | ⚒️ 需要 workflow |
| app 镜像 Containerfile | `FROM runtime` + pip install vllm + plugin-FL | ⚒️ 需要 Containerfile |
| 构建后冒烟测试 | `docker run --rm ... python3 -c 'import vllm'` | ⚒️ 需要 CI step |

### 3.2 无法（完全）自动化

| 任务 | 原因 |
|------|------|
| vllm 版本升级时复查 config.yaml 规则 | 新版本可能引入需加入 `remove_*` 的新依赖；`repack_recursive` 能自动发现声明 torch/triton 的间接依赖，但顶层黑名单（CUDA-only、orphaned）仍需人工判断 |
| 各平台集成测试 | 各厂商 torch 构建、ABI、设备特性不同 |
| FlagGems 版本升级 + tag | 需与 FlagGems 团队协调 |
| 模型下载 | 环境相关，大文件，需适当存储 |

## 4. 风险与痛点

**风险：**

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| vllm 版本升级引入新黑名单依赖 | 中 | 每次升级检查 METADATA diff，更新 config.yaml `remove_*` |
| 间接依赖声明不兼容 torch 版本 | 中 | `repack_recursive()` 自动发现并剥离；监控 pip install 输出 |
| pip 解析行为变化 | 低 | 已从 uv 迁移到 pip；pip 升级时重新测试 |
| Vendor PyPI token 过期/更改 | 低 | CI 用 secrets；文档记录 token 轮换 |
| macOS vs Linux 平台不匹配 | 中 | 永不在 macOS 上 repack；CI 在 H20 runner 上跑 |
| vllm 二进制 wheel ABI 不兼容 | 低-中 | 警告可接受；生产需源码构建（仅 standard/NVIDIA 相关） |
| FlagGems 未来又硬锁其他依赖 | 中 | 已遇 numpy + sqlalchemy；FlagGems 应用 `>=` 而非 `==` |

**痛点：**

| 痛点 | 严重度 | 备注 |
|------|--------|------|
| wheel 上传 2-3 min/厂商 | 中 | CI 可接受，多厂商可并行 |
| pip 依赖解析慢（vllm 82 deps，3-5 min） | 低 | Docker build 一次性成本，layer 有缓存 |
| FlagGems 硬锁依赖级联冲突 | 中 | `sqlalchemy==2.0.48` 装了又被卸；应审查 FlagGems 其他硬锁 |
| 节点上无模型文件 | 低 | 每个模型下载一次，用 `/data/models` 存储 |

## 5. 设计决策记录（ADR）

### 5.1 版本号 `+flagos` 后缀（2026-08-01）

**决策：** repack 后的 wheel 统一加 `+flagos` 本地版本后缀，**保持**原始
platform tag（`py3-none-any`），不伪造 `cp38-abi3-manylinux_2_35_x86_64`。

**理由：**
1. PEP 440：`0.20.2+flagos > 0.20.2`，pip 版本解析优先选我们的 repacked wheel。
2. 伪造 platform tag 会声明不存在的 ABI 要求，造成误导。
3. `+flagos` 明确标识 wheel 出自 FlagOS repack 流程。

**验证状态（mthreads 实证）：**

| 验证项 | 状态 | 结论 |
|--------|------|------|
| pip 版本排序偏好 `+flagos` | ✅ mthreads | 单步 `vllm==0.20.2+flagos` 正确命中，torch 未降级 |
| vendor + Aliyun 混合索引 | ✅ mthreads | `--index-url vendor --extra-index-url aliyun` 正确解析，131 包零泄漏 |
| 平台匹配 vs 版本比较优先级 | ✅ mthreads | 保留 `py3-none-any` 情况下版本号（`+flagos`）优先于平台匹配度，pip 选中我们的 wheel |
| 缓存干扰 | ⬜ | 未系统测试 pip 缓存是否跳过版本比较 |
| 跨后端正式验证矩阵 | ⬜ | 仅 mthreads 实证；MetaX/其他 empty 后端待用单步流程回归 |

**若跨后端回归发现 pip 选错版本，备选：** 改用 `0.20.2.post1`（非本地
版本，排序明确高于 `0.20.2`）。

**相关提交：** `main` 478de6b、PR #280（递归 `+flagos` pin，使单步安装成立）。

### 5.2 empty vllm 包的通用性（待办）

empty build 是纯 Python（无硬件代码），repack 只清理 METADATA 依赖声明、
不改代码，输出 `py3-none-any`——理论上**一份 wheel 通用于所有 empty 后端**：

```
Build once (任意 empty 后端)  →  Upload to ALL vendor PyPIs
```

安装时从目标后端 PyPI 取该后端的 torch 等依赖即可。

**待实现（⬜）：**
1. 扩展 `build-and-repack.sh --upload` 支持一次上传到全部 vendor PyPI。
2. 或建通用 workflow：build once → upload to all。

**参考：** FlagGems Python 包已采用此工作流。**前置：** 此模型对 NVIDIA
成立与否取决于 §5.3。

### 5.3 NVIDIA 是否统一 empty 模式（基准测试门控，未决）

**现状：** NVIDIA 用 standard 构建（官方预编译 wheel，含 vllm 自带 CUDA
kernel）；其余后端用 empty + plugin-FL/flag_gems 算子。

**未决问题：** 是否让 NVIDIA 也走 empty，从而全线统一、`+flagos` empty wheel
真正"一份通用"（§5.2）。

**决策标准（基准测试门控）：**
- 需要一次 NVIDIA 上 **standard vs empty** 的推理性能基准（吞吐 / 延迟）。
- **若 empty 模式性能可接受** → 全线统一 empty（含 NVIDIA），§5.2 成为正式模型。
- **若性能严重下降** → NVIDIA 保留 standard 构建，empty 仅用于非 NVIDIA 后端。

**权衡：** standard 用 vllm 调优过的 CUDA kernel（paged attention、fused MoE
等），通常最快、与上游对齐；empty 放弃这些，改由 flag_gems（Triton）提供，
换取全线统一与单一可移植 wheel。NVIDIA 是唯一不需要 empty 变通的后端，
潜在性能损失最值得担心。

**前置任务：** 见 §2.1 待办的 empty-mode 性能基准。**在基准数据出来前，
本报告不对本问题下结论。**

## 6. 演进与经验（弯路记录）

标准流程（§1）不是一开始就有的，是三个后端踩坑收敛出来的。这里记录主要
弯路，供回看"为什么规则是现在这样"：

- **numpy 版本 saga（§2.1）** —— 曾三次改法：(a) FlagGems 设 pip 推荐的
  `numpy==2.3.5` 并打 tag `v5.3.2` → Python 3.10 后端不支持 `numpy>2.2.6`；
  (b) 把 numpy 下沉到各后端；(c) FlagGems 干脆不 pin numpy。最终稳定在
  §1.7：**FlagGems 不 pin，build-infra 按后端锁定**（3.12→2.3.5, 3.10→2.2.6）。
- **FlagGems tag 复用** —— 过程中出现过删除 `v5.3.2` 再用同名重打。破坏
  可复现性，**不应再做**——bug 修复用递增新 tag（§1.6）。
- **伪造 platform tag（§2.2）** —— MetaX 曾把 `py3-none-any` 改写成
  `cp38-abi3-manylinux...` 来抢过 Aliyun 原版。§5.1 否定：`+flagos` 版本号
  排序已足够，伪造 ABI 有害。
- **两步 `--no-deps` 安装（§2.2）** —— MetaX 曾因间接依赖 torch 泄漏被迫
  两步锚定。PR #280 递归 pin `+flagos` 后，单步安装即安全（§1.4），
  mthreads 实证。
- **`also_repack` 手工列表 → 递归发现** —— 早期手工维护"还需 repack 的
  间接依赖"列表；现由 `repack_recursive()` 在 repack 时解析实际依赖树自动
  发现，手工列表已废弃（§1.3）。
- **`--extra-index-url` 优先的误解（§2.1）** —— 早期以为 extra-index 会被
  pip 优先；实际 pip 拉平所有索引按版本号选。让我们的 wheel 胜出的始终是
  `+flagos` 版本号，与索引主次无关。
