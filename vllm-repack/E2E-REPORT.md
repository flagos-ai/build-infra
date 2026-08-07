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
- **第 2 部分（后端验证记录）** 是五个已验证后端的实测记录，作为标准流程的
  worked example。其中 NVIDIA 是首个跑通、也是唯一使用标准构建的后端；
  MetaX 是首个 `empty` 后端；mthreads 是标准流程的范例来源；hygon 首次证明
  **repacked wheel 跨后端通用**（直接复用 mthreads 上打包的 `+flagos` wheel）；
  iluvatar 是首个**推理跑不通的负结果**（厂商 corex Triton fork + torch 2.7.1
  相对 vllm 0.20.2 原生 kernel 过旧）。个别后端因历史原因走过弯路，记录中已
  标注哪些步骤已被标准流程取代。

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
1. **按包剥离特定声明** —— `strip_from_indirect` 对每个受审依赖统一生效；
   个别包需要**更窄**、只针对该包的剥离。`config.yaml` 的
   `strip_extra_from_indirect`（键为包名、值为要剥的依赖名）实现这一点。
   当前用于 `opencv-python-headless: [numpy]`——opencv 声明的 `numpy>=2` 是
   faked 下限（§1.7），剥掉它才能让 numpy-1.x 后端单步安装（§1.4）。numpy
   **不**放进全局 `strip_from_indirect`，因为别的包可能把 numpy 声明为真实
   ABI 下限——此 map 把剥离精确限定在 opencv。opencv 是二进制 wheel，repack
   读取并保留其平台 tag（`repack_dep` 复用 `repack_top_level` 读 WHEEL Tag
   的逻辑），输出文件名不再误退化为 `py3-none-any`。
1. **保留二进制 wheel 的平台 tag（重要修正）** —— 此前 `repack_dep` 对所有
   间接依赖硬编码输出 `py3-none-any`。这对纯 Python 包（vllm、compressed-
   tensors）正确，但对**二进制**间接依赖是错的：opencv 与 **xgrammar** 都是
   binary wheel（opencv `cp37-abi3-manylinux_2_28_x86_64`、xgrammar
   `cp310-cp310-manylinux_2_27_x86_64`），过去被误标成 `py3-none-any`——一份
   x86_64 的 `.so` 挂着"通用"标签，装到别的平台会静默塞入不可用的二进制。
   修正后 repack 保留真实平台 tag，pip 装机时按 arch/pyver 自动选对，平台不
   匹配则**明确拒绝**而非静默装坏。这也界定了"通用性"的粒度：vllm、
   compressed-tensors 是真正 `py3-none-any` 的通用 wheel；**opencv、xgrammar
   是 ABI 绑定的二进制 wheel**——opencv 是 `cp37-abi3`（稳定 ABI，一份跨所有
   CPython≥3.7，仅随 arch 变），xgrammar 是 `cp310-cp310`（**随 Python 小版本
   变，也随 arch 变**）。正因如此，四个 wheel 全部**留在 per-vendor 索引**
   （`flagos-pypi-<vendor>`）：每个 vendor runtime 镜像只有单一 (python, arch)，
   `build-and-repack.sh <vendor>` 在该镜像里跑就自然产出唯一正确的 opencv/
   xgrammar 变体，与该后端的 torch/flag_gems 并列——无需枚举 Python 版本、无
   矩阵可维护，且 vllm 与其匹配的 xgrammar 始终同源同批（bump vllm 时重跑
   repack 整批重生，不会出现跨索引版本错配把 triton 泄漏放回来）。曾短暂设想
   过 shared `flagos-pypi-hosted`，但 xgrammar 的 per-Python-version 特性会让
   共享索引要么维护 3×2 矩阵、要么拆成多索引安装——反而更脆，故放弃（§5.2）。

顶层剥离规则（`config.yaml`）：`remove_torch_chain`（torch/torchaudio/
torchvision/torchcodec）、`remove_cuda_only`（PyNvVideoCodec、nvidia-* 等）、
`remove_orphaned`（随上游一起失去消费者的包，如 apache-tvm-ffi）。

## 1.4 安装与验证流程

`+flagos` 后缀让安装收敛为**单步**。所有 repacked wheel（vllm + xgrammar +
compressed-tensors + opencv-python-headless）与 vendor 专属包（torch/flag_gems/
flagtree）同住 per-vendor 索引；其余安全依赖来自 Aliyun：

```bash
VENDOR=https://resource.flagos.net/repository/flagos-pypi-<vendor>/simple
ALIYUN=https://mirrors.aliyun.com/pypi/simple

# 1. 运行时依赖 —— 版本锁定依据 configs.yaml 的对应后端
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" \
  <torch/torchvision/... 见 configs.yaml deps> flag_gems==<configs.yaml flaggems> \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.1 numpy==<per-backend, 见 §1.7>

# 2. repacked vllm —— vendor 为主索引，单步即可，无需 --no-deps
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

> **numpy-1.x-ABI 后端（iluvatar、hygon）也单步。** 这些后端 torch 编于
> numpy 1.x，必须 `numpy==1.26.4`（§1.7）。曾经把它写进第 1 步会触发
> `ResolutionImpossible`——`opencv-python-headless` 强声明 `numpy>=2`（faked
> 下限，§1.7），pip 解析期不认运行时兼容。**现已修复：** repack 把
> opencv 的 `numpy` 声明一并剥掉（`config.yaml` 的
> `strip_extra_from_indirect`，与剥 torch/triton 同机制），repacked
> `opencv-python-headless==5.0.0.93+flagos` 不再声明 numpy 下限。因此
> `numpy==1.26.4` 可直接写进第 1 步，所有后端单步安装，不再需要两步降级。
> opencv 是二进制 wheel（`cp37-abi3-manylinux_2_28_<arch>`），repack 只改
> METADATA、保留平台 tag；因为它随 per-vendor 镜像在对应 (python, arch) 上
> repack 并传到该 vendor 索引，无需跨平台矩阵，pip 装机时命中的就是本机的
> wheel。

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
- **hygon-dtk26.04（Python 3.10）：应为 `numpy==1.26.4`** —— 其厂商 torch
  编于 numpy 1.x ABI，不能跑 numpy 2.x（§2.4）。当前 pin 的 `2.2.6` 是坏的。

**真正决定 per-backend numpy 版本的两个约束：**
1. **Python 版本上限** —— py3.10 不支持 `numpy>2.2.6`。
2. **厂商 torch 的 numpy ABI** —— torch 编于哪个 numpy ABI 决定其运行时下限/
   上限（编于 1.x 的 torch 要 `<2`；编于 2.x 的向后兼容 1.x）。

`opencv-python-headless` 声明的 `numpy>=2` **不是真实约束**——它是针对 numpy
2.x 编译、运行时向后兼容 1.x 的 wheel，实测在 numpy 1.26.4 上功能完好（§2.4）。
历史上的 numpy bump/revert 有一半是被这个 faked 声明误导的（见 §6）。

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

五个后端按第 1 部分的模板组织：**环境 → repack → 安装 → 阻塞点 → Stack
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

> **事后更正（§2.4）：** 上面这个"冲突"其实是**伪冲突**——opencv 的
> `numpy>=2` 是 faked 声明，其 wheel 编于 numpy 2.x 但运行时向后兼容 1.x
> （实测 1.26.4 下 C-API 往返完好）。当时若识破这一点，本可继续沿用全局
> `numpy==1.26.4`，无需 bump/revert。真实约束只有 py 版本上限与厂商 torch
> ABI 两条（§1.7）。

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

## 2.4 hygon-dtk26.04（跨后端通用性验证）

**日期:** 2026-08-02　**平台:** Hygon BW1000 (8× HCU)
**节点:** `hygon25`（JumpServer 别名，hostname hygon-2-25）　**DTK:** 26.04
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-hygon-dtk26.04:2.1.1`

**这是首个不做本地 repack、直接复用他机 wheel 的后端**——用的正是 §2.3 在
mthreads 上打包上传到 `flagos-pypi-mthreads` 的三个 `+flagos` wheel。目的有
二：(1) 实证 §5.2 的"empty wheel 跨后端通用"；(2) 摸清 Hygon 上 vllm 推理
的坑。结论：**通用性成立**，唯一真阻塞是镜像侧的 torch↔numpy ABI 不匹配。

> **容器启动（DCU 直通）：** docker 默认 runtime 已是 `dcu`；仍显式带上设备
> 与 HAL 挂载：
> ```bash
> docker run -d --name vllm-verify-hygon --network host --runtime dcu \
>   --device /dev/kfd --device /dev/mkfd --device /dev/dri --group-add video \
>   -v /opt/hyhal:/opt/hyhal -v /data:/data \
>   harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.1 sleep infinity
> ```
> `hy-smi` 在容器内可见 8× HCU（宿主机无此命令）。

### Repack —— 无（复用 mthreads 产物）

不在 Hygon 上重新 build/repack。empty vllm 是纯 Python `py3-none-any`，repack
只清理 METADATA 依赖声明、不含硬件代码，因此**一份 wheel 通用于所有 empty
后端**（§5.2）。直接从 `flagos-pypi-mthreads` 装 §2.3 的三个包：

| 包 | 版本 | 来源 |
|------|------|------|
| vllm | 0.20.2+flagos | `flagos-pypi-mthreads`（§2.3 打包） |
| xgrammar | 0.2.5+flagos | 同上 |
| compressed-tensors | 0.15.0.1+flagos | 同上 |

### 安装 —— ✅ 单步，零泄漏（跨后端通用性实证）

按 §1.4 单步安装，但**主索引指向 mthreads 的 PyPI**（而非 hygon 自己的）：

```bash
VENDOR=https://resource.flagos.net/repository/flagos-pypi-mthreads/simple
ALIYUN=https://mirrors.aliyun.com/pypi/simple
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" vllm==0.20.2+flagos
```

`pip install --dry-run` 的 "Would install" 集合中**零** torch / triton /
numpy / nvidia-* / flag_gems——Hygon 镜像烘焙的版本全部保留：

- `torch` 保持 `2.9.0+das.opt1.dtk2604`（未降级），`triton` 不存在（由
  flagtree 提供，与 mthreads 同）
- `flag_gems` 5.3.2 / `flagtree` 0.5.1+hcu3.1 / `numpy` 2.2.6 全部完好
- 三个 `+flagos` wheel 正确解析
- `vllm-plugin-FL` 纯 Python 安装（`0.0.0+gd1327ae0a`，不设 `VLLM_VENDOR`），
  `fl` 插件正常激活

**这实证了 §5.2：mthreads 上打的 empty wheel 在 Hygon 上原样可用，vendor
PyPI 无须为这些纯 Python 包做 per-vendor repack。**

### 阻塞点：torch↔numpy ABI 不匹配（镜像侧问题，非 vllm 引入）

装完后 `import torch` 警告 `Failed to initialize NumPy: _ARRAY_API not
found`，`tensor.numpy()` 抛 `RuntimeError: Numpy is not available`。

**根因：** 厂商 torch `2.9.0+das.opt1.dtk2604` 编译时链接的是 **numpy 1.x C
ABI**，而镜像烘焙的是 **numpy 2.2.6**（configs.yaml 的 hygon pin）。二分验证：
numpy 1.26.4 → `TORCH_NUMPY_OK`；numpy 2.2.6 → `Numpy is not available`。
**并非 vllm 引入**——numpy 全程保持 2.2.6（安装未改动它），torch 在 baseline
就已经用不了 numpy。与 iluvatar 同类（其 torch 亦编译于 numpy 1.x）。

**挤压效应（伪冲突）：** vllm 依赖 `opencv-python-headless 5.0.0.93` 声明
`numpy>=2; python_version >= "3.9"`，看似与 Hygon torch 的 `numpy<2` 冲突。
**但这个 `>=2` 是 faked（打包策略声明，非运行时 ABI 下限）。** 实测：numpy
1.26.4 下 cv2 5.0.0 的 C-API 往返全部正常——`cvtColor`、`imencode`/`imdecode`
（PNG 无损，`max_err=0`）、`resize`(float64) 均通过。技术原因：numpy 2.0
起，**针对 numpy 2.x 编译的 C 扩展在运行时向后兼容 numpy ≥1.19**，所以
opencv wheel 在 1.26.4 上照跑，只是元数据声明了 `>=2`。因此 opencv **不构成**
numpy 版本的真实约束（这也纠正了历史 numpy saga 的一个前提，见 §1.7、§6）。

**真正的 numpy 下限是厂商 torch 的 ABI，且是非对称的：**
- 针对 numpy **1.x** 编译的 torch（hygon）→ 运行在 numpy 2.x 上**前向不兼容**
  → 硬性要求 `<2`，不可 fake。
- 针对 numpy **2.x** 编译的扩展（opencv、多数后端 torch）→ 向后兼容 1.x。

**修复属镜像侧，两个方向：**
- **(b) configs.yaml 给 hygon pin `numpy==1.26.4`**（即时、在我方掌控内；
  opencv 既是 faked，此路无副作用）——**推荐的即时修复**。
- **(a) 厂商用 numpy 2.x 重编 torch**（与其余后端一致，但需厂商行动、周期长）。

当前 `configs.yaml` 的 `hygon: numpy==2.2.6` 与所发 torch wheel 不兼容——短期
按 (b) 改 1.26.4，同时把 (a) 反馈给构建 DTK26.04 torch wheel 的一方。

> **flag_gems mul 门控 #5130 不影响 Hygon：** Hygon 报
> `device.type=='cuda'`、`torch.cuda.device_count()==8`、flag_gems
> `runtime.device.name=='cuda'`——与 MetaX 同，非 mthreads 的 `"musa"`。故
> §2.3 的 mul 门控回归在此为 no-op。

### serve + 推理 —— ✅ 成功（以 numpy 1.26.4 绕过上述 ABI 阻塞）

选 **Ministral-8B-Instruct-2410-FlagOS**（简单 rope，变量最少）：

```bash
vllm serve /data/Ministral-8B-Instruct-2410-FlagOS --port 8033 \
  --trust-remote-code --max-model-len 4096 --enforce-eager \
  --gpu-memory-utilization 0.85 --tensor-parallel-size 1
```

serve 到达 `Application startup complete`，flag_gems 算子经插件正确分发：

```
Op 'rms_norm' using 'default.flagos' (kind=flagos, vendor=None)
Op 'rotary_embedding' using 'default.flagos' (kind=flagos, vendor=None)
Op 'silu_and_mul' using 'default.flagos' (kind=flagos, vendor=None)
```

```json
{"choices":[{"text":" Paris. It is the most populous city in France and the country's center of politics, culture, fashion, food, and art. Paris is known for",
  "finish_reason":"length"}]}
```

✅ 除 numpy 绕过外，本模型无需任何 Hygon 专属 plugin / flag_gems 改动。

### Stack 验证

```
torch:        2.9.0+das.opt1.dtk2604  ✅  from 镜像（未降级）
triton:       (absent)                ✅  DTK 无 triton，由 flagtree 提供
flagtree:     0.5.1+hcu3.1            ✅
flag_gems:    5.3.2                   ✅  mul 门控 #5130 不影响（device=cuda）
numpy:        1.26.4 (绕过)           ⚠️  镜像默认 2.2.6 与 torch ABI 不匹配
vllm:         0.20.2+flagos           ✅  empty, 复用 mthreads PyPI 产物
xgrammar:     0.2.5+flagos            ✅  复用 mthreads PyPI 产物
compressed-t: 0.15.0.1+flagos         ✅  复用 mthreads PyPI 产物
vllm_fl:      0.0.0+gd1327ae0a        ✅  纯 Python（无 VLLM_VENDOR）
HCU device:   ✅ 8× 可见               hy-smi (Hygon BW1000)
vllm serve:   ✅ 启动成功              TP=1, enforce-eager, gpu-util 0.85
Inference:    ✅ 成功                  Ministral-8B, 32 tokens
```

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| 镜像侧 torch↔numpy ABI | ⬜ 阻塞 | 反馈厂商重编 torch（numpy 2.x），或 configs.yaml pin numpy 1.26.4 |
| 一份 wheel 上传到全部 vendor PyPI | ⬜ | 通用性已实证（§5.2），待自动化多厂商上传 |
| 更大模型 / TP>1 / yarn rope | ⬜ | 仅测过 Ministral-8B + eager + TP=1 |

**相关提交：** 无新增代码；复用 §2.3 mthreads 的 repack 产物（PR #280）。

## 2.5 iluvatar-corex4.4.0（负结果：厂商工具链版本过旧）

**日期:** 2026-08-02　**平台:** Iluvatar CoreX (BI 系列)
**节点:** `ix15`（JumpServer 别名，hostname n15）　**CoreX:** 4.4.0
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-iluvatar-corex4.4.0:2.1.1`

**这是首个跑不通推理的后端**，但结论明确、可操作。与 §2.4 hygon 一样直接
复用 mthreads 的 `+flagos` wheel，验证三件事：(1) wheel 跨后端通用；(2) numpy
版本正确；(3) vllm 推理可跑。前两点通过，第三点**失败**——根因是 iluvatar 的
**corex Triton fork 前端 + torch 2.7.1 相对 vllm 0.20.2 的原生 kernel 过旧**。

### Repack —— 无（复用 mthreads 产物）

同 §2.4，不在 iluvatar 上重新 build。直接从 `flagos-pypi-mthreads` 装 §2.3 的
三个 `+flagos` wheel（vllm 0.20.2 / xgrammar 0.2.5 / compressed-tensors 0.15.0.1）。

### 安装 —— ✅ wheel 通用；曾踩到 numpy 单步安装坑（现已修复）

**GOAL 1（wheel 通用性）✅：** 三个 mthreads `+flagos` wheel 在 iluvatar 上
正常安装，torch `2.7.1+corex.4.4.0`、flag_gems、flagtree 全部保留，零泄漏。
**这是 §5.2 通用性的第二个跨后端实证**（继 hygon 之后）。

**GOAL 2（numpy 版本）✅：** iluvatar torch 2.7.1 同样编于 numpy 1.x ABI，
`configs.yaml` 已 pin `numpy==1.26.4`（正确，`tensor.numpy()` 可跑）。

> **当时的坑（现已修复）：** 单步 `pip install vllm==0.20.2+flagos
> numpy==1.26.4` 曾报 `ResolutionImpossible`——`opencv-python-headless` 强声明
> `numpy>=2`（§1.7 的 faked 下限），pip 解析期不认"运行时兼容"，当时只能两步
> 安装（先装 vllm 让 numpy 浮到 2.2.6，再 `pip install numpy==1.26.4` 降级）。
> **修复：** repack 现在把 opencv 的 `numpy` 声明一并剥掉（`config.yaml` 的
> `strip_extra_from_indirect: {opencv-python-headless: [numpy]}`，§1.3），
> repacked `opencv-python-headless==5.0.0.93+flagos` 不再声明 numpy 下限，
> `numpy==1.26.4` 可直接写进第 1 步——所有 numpy-1.x-ABI 后端（iluvatar、
> hygon）单步安装即可，两步绕过成为历史（§1.4）。

### 阻塞点：corex Triton fork + torch 2.7.1 对 vllm 0.20.2 原生 kernel 过旧

**GOAL 3（推理）❌**。四个阻塞点，同一根因。iluvatar 的 torch 2.7.1 是四个
后端里最旧的（hygon 2.9.0、mthreads 2.9.1、metax 2.8.0、nvidia 2.10.0），
corex Triton fork 前端也比 vllm 0.20.2 的原生 kernel 所需的更旧、更严格：

| # | 现象 | 性质 | 绕过手段 |
|---|------|------|----------|
| A | `import vllm` 崩：`ImportError: cannot import name '_SymmetricMemory' from 'torch._C._distributed_c10d'` | torch 2.7.1 < 2.8（`_SymmetricMemory` 约 torch 2.8 引入） | vllm `parallel_state.py:42` 的 `import torch.distributed._symmetric_memory` 是**无守卫**的顶层导入；而 vllm 自己在**同类文件** `symm_mem.py:16` 已用 `try/except ImportError` 守卫。给 line 42 补同样的守卫即可 import——TP=1 下 symm_mem 路径根本不走（实际算子在 `parallel_state.py:245` 的 `torch.ops.symm_mem.*`，是 TP>1 collective） |
| B | 采样阶段 Triton 编译崩：`TypeError: Cannot use /, #, or % with triton.language.uint32 and triton.language.int32 ... different signedness` | corex Triton fork 拒绝混合符号运算 | vllm 原生采样 kernel `topk_topp_triton.py` 的 `uint32 // int32`。在 `topk_topp_sampler.py` 强制 `HAS_TRITON=False`，回退到纯 pytorch 采样路径 |
| C | 推理阶段 Triton 编译崩：`AttributeError("'AnnAssign' object has no attribute 'targets'")`，出错行 `left: tl.int32 = 0` | corex Triton 前端解析不了 PEP 526 注解赋值 | vllm 原生 attention kernel `triton_unified_attention.py`。用 plugin 自带 flag `VLLM_FL_USE_FLAGGEMS_ATTN=1` 把 attention 路由到 plugin 的 `AttentionFLBackend`（flag_gems attn，能在 corex 上编译），替代 vllm 原生 `TRITON_ATTN`（默认值，崩）——**这是 plugin 提供的正规开关，非源码 hack** |
| D | 绕过 A–C 后 serve 启动成功（health 200、模型可列），但推理输出**乱码** | 前向数值正确性 | 未找到 |

**关键区分：flag_gems 自带的 Triton kernel（rms_norm、rotary_embedding、
silu_and_mul）在 corex 上编译运行都正常**——它们是针对 corex fork 写的；崩的
全是 **vllm 上游自带的原生 Triton kernel**（B 的采样、C 的 attention），用了
corex 前端不支持的语言特性。

**D 是决定性的坏消息：** 绕过 A–C 后，serve 完整启动、接受请求、返回 24
tokens、HTTP 200，但输出是乱码：`"eld \$不断 the movie...髹 Next..."`。在
**temp=0（确定性 argmax，无采样随机性）** 下**仍是乱码**（`"eld \`vette记者在
ApplicationController\n\n..."`，chat 全是换行）——排除采样，故障锁定在
**前向数值路径**：模型跑完并返回，但 logits 数值是错的。日志里
`rms_norm=['native']`（部分算子回退 torch-native）可能也参与了失配。

> **对照 hygon/mthreads：** 那两个后端 torch ≥2.8、厂商 Triton fork 能吞下
> vllm 原生 kernel，所以只碰到单点的 mul 门控 bug（可修）。iluvatar 不是一个
> bug，是**工具链代差**——corex Triton 前端与 torch 2.7.1 双双落后于 vllm
> 0.20.2 的要求。A、B 施加的都是**诊断补丁**（非生产修复），到 D 停手未再
> 深挖数值 bug。
>
> **注意（诊断组合的局限）：** 强制 flag_gems attention（C）+ 关闭原生采样
> Triton（B）是一个**未经测试的算子组合**，尚不能完全排除它本身就是 D 乱码
> 的成因之一。要定论需在一个 Triton 无障碍的后端上复现同样的
> `VLLM_FL_USE_FLAGGEMS_ATTN=1` + `HAS_TRITON=False` 组合做对照。

### serve + 推理 —— ❌ 乱码（前向数值错误）

```bash
VLLM_FL_USE_FLAGGEMS_ATTN=1 vllm serve /data/Qwen3-4B-Instruct-2507-FlagOS \
  --port 8035 --trust-remote-code --max-model-len 4096 --enforce-eager \
  --gpu-memory-utilization 0.85 --tensor-parallel-size 1
# 另需 A/B 两处诊断补丁：parallel_state.py:42 加守卫、topk_topp_sampler.py HAS_TRITON=False
```

serve 到达 `Application startup complete`，`Using FlagGems attention backend.`，
KV cache 127,024 tokens。但推理（含 temp=0）输出乱码：

```json
{"choices":[{"text":"eld \\`vette记者在 ApplicationController\n\n\n...","finish_reason":"length"}]}
```

### Stack 验证

```
torch:        2.7.1+corex.4.4.0    ✅  from 镜像（未降级，四后端中最旧）
triton:       corex fork           ⚠️  flag_gems 自带 kernel 可编译；vllm 原生 kernel 不可
flagtree:     (镜像自带)            ✅
flag_gems:    5.3.2                 ✅  自带算子编译运行正常（mul 门控 #5130 不影响，device=cuda）
numpy:        1.26.4               ✅  configs.yaml 已 pin（torch 编于 numpy 1.x ABI）
vllm:         0.20.2+flagos        ✅  empty, 复用 mthreads PyPI 产物
vllm_fl:      0.0.0+gd1327ae0a     ✅  纯 Python（无 VLLM_VENDOR）
CoreX device: ✅ 可见               (Iluvatar BI)
vllm import:  ⚠️  需补 symm_mem 守卫（trap A）
vllm serve:   ⚠️  需 B+C 绕过才能启动
Inference:    ❌  乱码（temp=0 仍乱）——前向数值错误（trap D）
```

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| 反馈厂商：corex Triton fork 支持 vllm 原生 kernel | ⬜ 阻塞 | 需支持混合符号运算（B）与 PEP 526 注解赋值（C）；或 FlagGems 提供覆盖全部 vllm 原生 Triton 算子的替代 |
| 反馈厂商：torch 升级到 ≥2.8 | ⬜ 阻塞 | vllm 0.20.2 需要 `_SymmetricMemory`（trap A），corex torch 2.7.1 缺 |
| 前向数值正确性（trap D）| ⬜ 阻塞 | flag_gems 在 corex 上逐算子对数值；先在无 Triton 障碍的后端复现 B+C 组合做对照，排除诊断组合本身 |
| vllm `parallel_state.py:42` 无守卫导入 | ⬜ 可提 upstream/plugin | vllm 自己在 `symm_mem.py:16` 已守卫同一导入；给 line 42 补 `try/except` 对所有 torch<2.8 后端都受益 |
| numpy-1.x 后端单步安装 ResolutionImpossible | ✅ 已修复 | repack 剥掉 opencv 的 faked `numpy>=2`（`strip_extra_from_indirect`，§1.3）；单步安装恢复，§1.4 已更新 |

**相关提交：** 无；复用 §2.3 mthreads 的 repack 产物（PR #280）。诊断补丁
（trap A/B）为一次性验证手段，未落库。

---

## 2.6 enflame-tops1.9.10（GCU300：flash_attn ABI 已解，剩 flag_gems flash 内核 int64）

**日期:** 2026-08-02（首测 2.1.1）/ 2026-08-06（重测 2.1.2）　**平台:** Enflame GCU300（8 卡）
**节点:** `enflame1`　**driver/tops:** 1.9.10　**arch:** `dtu-enflame-tops--gcu300`
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-enflame-tops1.9.10`（2.1.1 → 2.1.2）
**容器:** 首测 `vllm-verify-enflame-v2`（2.1.1）；重测 `vllm-verify-enflame-212`（2.1.2）

与 §2.4 hygon 一样跑通用性验证。**2.1.1 首测：**安装/插件通过、serve 启动完成、
推理被 attention 阻塞（flash_attn ABI + FlagGems int64 两个上游缺口）。**2.1.2 重测
（§2.6.1）：**flash_attn ABI 已随 **PR #310** 解决，serve 推进到 flag_gems flash
内核，只剩 **FlagGems `flash_varlen_fwd_kernel` int64** 一个阻塞点（待 GCU 专属
int32 内核，§2.6.1 末尾）。GCU300 的核心约束贯穿全程：**其 triton 后端
（`make_gcuir` 的 PassManager）彻底拒绝 64 位数据类型**——不是前端 / FlagTree
问题，换 triton 前端无用，拒绝发生在 GCU300 codegen 后端。

### Repack —— 在 enflame 上重新 build（cp312）

enflame Python 3.12，xgrammar 是 cp312-locked 二进制，无法复用 hygon 的 cp310
产物，故在镜像内重新 build empty vllm 并 repack（`+flagos`）。

### 安装 —— ✅ 零泄漏（走真实自动化路径，非 --find-links）

`pip install --index-url flagos-pypi-enflame --extra-index-url aliyun 'vllm==0.20.2+flagos'`：
**setuptools 稳定在 83.0.0**（torch_gcu 解钉后不再降级到 69.5.1），
torch `2.10.0+cpu` / torch-gcu `2.10.0` / numpy `2.3.5` 全保留，依赖全为
`+flagos`（xgrammar 0.2.3、compressed-tensors 0.15.0.1、opencv-headless 5.0.0.93），
无公有 torch/cuda/triton 链，无 pip 冲突。8 GCU 可见。

> **背景：** enflame 曾是唯一 setuptools 被硬钉（69.5.1）的后端，根因是
> **torch_gcu 的 `Requires-Dist: setuptools ==69.5.1`**（build-infra 从不钉运行时
> setuptools；FlagGems 的 `<77` 是 build-only、装完不可见）。厂商侧已 repack
> torch_gcu 去掉该钉并重建镜像，本次验证即在该镜像上。

### 插件 —— ✅ 干净安装（--no-build-isolation，纯 Python）

全历史 clone（非 `--depth 1`）+ `pip install --no-build-isolation -e .`，
`VLLM_VENDOR` 未设 → `ext_modules=[]`，纯 `py3-none-any`，版本
`0.2.0+gd1327ae0a`（正规 setuptools-scm）。厂商自动识别（flag_gems
DeviceDetector）：vendor=enflame、device_type=gcu、dist=eccl，无需手动 env。

### 2.1.2 重测记录（2026-08-06）—— flash_attn ABI 已解，逐层推进到 flag_gems flash 内核

镜像 `flagos-runtime-enflame-tops1.9.10:2.1.2`，容器 `vllm-verify-enflame-212`
（`--privileged -v /dev:/dev`，模型 Qwen3-4B 下载自 ModelScope `Qwen/Qwen3-4B`，
`Qwen/Qwen3-4B-Instruct` 在 ModelScope 上 404）。逐层结果：

| # | 层 | 结果 |
|---|-----|------|
| 1 | flash_attn ABI（原阻塞 1） | ✅ **已解决**。`import flash_attn`（2.7.2）/ `flash_attn_gcu` 正常（`LD_LIBRARY_PATH` 补 `torch/lib` + `torch_gcu/lib`）。PR #310 把 deps 钉改为 `flash-attn==2.7.2+torch.2.10.0.gcu.3.4.20260506` |
| 2 | 镜像双编译器落地 | ❌ **`compiler triton` 默认不可用**（见下"双编译器缺口"）；FlagTree 默认可 import 但 flash_attn 的 unguarded `import triton_gcu.triton` 失败。最终以 vendor triton + `TRITON_BACKENDS_IN_TREE=1` 跑通 |
| 3 | 模型加载（TP=8, Qwen3-4B） | ✅ 3/3 shards、weights 3.8s |
| 4 | torch.compile（inductor） | ❌ `torch._inductor.codecache.get_system` 读 `device_properties.gcnArchName` —— `torch_gcu._GcuDeviceProperties` 无此属性 → `BackendCompilerFailed`。**`TORCHDYNAMO_DISABLE=1` 绕过** |
| 5 | embedding（`get_masked_input_and_mask` → `sub`） | ❌ flag_gems `gcu300/ops/sub.py`（pointwise-dynamic）在 vendor triton 上 `make_gcuir` 崩。**`sub` 加入 gcu.yaml 黑名单**回退 torch_gcu 后过 |
| 6 | attention 后端选择 | ❌ gcu.py `attention_backend` 硬编码 `FLASH_ATTN` + `sys.modules["vllm.vllm_flash_attn"]=flash_attn.vllm_flash_attn`；但 vendor `vllm_flash_attn/__init__.py` `from ._vllm_fa2_C import ...` —— **empty wheel 无该 C 扩展** → `assert vllm_flash_attn_version is not None` 崩。**gcu.py 加回退**：`_vllm_fa2_C` 不可导入时返回 `AttentionFLBackend` |
| 7 | 推理首次前向（attention） | ❌ `AttentionFLBackend.forward` → `flag_gems.ops.flash_api.py:579 mha_varlan_fwd` → `flash_varlen_fwd_kernel` **int64 指针/步长** → GCU300 `make_gcuir` 拒。**这就是 §2.6 记录的 FlagGems int64 阻塞，现于推理路径坐实** |

**双编译器缺口（镜像落地问题，非 vllm/plugin；已由 PR #332 解决）：**
- **FlagTree**（`/flagos` triton）是独立 fork，内嵌 `triton/backends/enflame/` +
  `_triton_gcu300.so`。**triton_gcu 是 vendor 对 upstream triton 的插件**，装在
  `/opt/triton`（`compiler triton` 切到此处）。
- `/opt/triton/triton/backends/` 只有 `amd/ nvidia/`，**没有 `enflame/`**；但
  FlagTree 的 dist-info（一直在 `importlib.metadata` 可见）声明 entry point
  `enflame = triton.backends.enflame` → `PYTHONPATH=/opt/triton` 下 `import triton`
  的 `_discover_backends()` 撞 `ModuleNotFoundError`，**连裸 `import triton` 都崩**。
- gcu300 wheel 的 `setup_distributed()` 声称"build 时已内嵌 patched triton"，但
  `/opt/triton/triton/backends/__init__.py` 无 `patched-by-triton-gcu` 标记，运行时
  回退 `safe_import_backends` 根本到不了。
- **重测时的 workaround：`TRITON_BACKENDS_IN_TREE=1`**（跳过 entry point 发现）→
  upstream triton 干净导入 → `triton_gcu.triton` 注册 `gcu` backend。实测
  flag_gems silu / vllm 0.20.2 / plugin fl 全通过。
- **根治（PR #332）：** 双编译器各装进独立 side dir——FlagTree → `/opt/flagtree`、
  Triton → `/opt/triton`，**都不进 site-packages**。dist-info 只在所在 compiler
  的 dir 在 PYTHONPATH 时可见 → entry point 互不泄漏，`TRITON_BACKENDS_IN_TREE=1`
  workaround 不再需要（hermetic 验证：flagtree 闲置在 /opt/flagtree 时
  `importlib.metadata` 报 0 个 `triton.backends` EP，`compiler triton` 切过去
  import/flash_attn/flag_gems 全通）。

**其他新发现（记入待办）：**
- `flash_attn/ops/triton/rotary.py`（新 wheel）对 `import triton_gcu.triton` **无守卫**
  （旧 2.9.1 wheel 有 try/except）——必须 triton_gcu 可导入才能 import flash_attn。
- TP=8 需要 `-v /dev:/dev`（raw flags）；toolkit flags 只给 64M `/dev/shm`，ECCL
  建共享内存段失败。
- ModelScope 下载需 `sudo mkdir` + `chown` 模型目录（`/public-flash/models` 是 root
  属主，secure 用户无写权）。

### GCU 专属 int32 flash_varlen_fwd_kernel（2026-08-06，FlagGems 侧工作）

**目标**（§2.6 待办）：给 enflame/gcu300 提供 int32 索引的 `flash_varlen_fwd_kernel`，
绕开 GCU300 对 64 位的拒绝，打通 attention 推理。

**实现**（`~/work/FlagGems`，未提交）：沿用 per-backend fork 惯例
（_hygon/_sunrise/_kunlunxin/_tsingmicro 同构），在
`src/flag_gems/runtime/backend/_enflame/gcu300/ops/` 下复制 generic 三件套并改：

| 文件 | 改动 |
|---|---|
| `flash_kernel.py` | `virtual_to_cache_offset` 的 `.to(tl.int64)` → `.to(tl.int32)`（2 处）——paged-KV 索引 int32 化 |
| `flash_api.py` | import 改 `.flash_kernel`；**philox_args 无 dropout 时分配 `torch.int32`**（原 `int64`）——去掉内核参数 `!tt.ptr<i64>` |
| `attention.py` | import 改 `.flash_api`/`.flash_kernel` |
| `__init__.py` | re-export `flash_attention_forward`/`flash_attn_varlen_func`/`flash_attn_varlen_opt_func` |

经 `SpecOpRegistrar`（arch=gcu300，`BackendArchEvent`）覆盖 `flag_gems.flash_attn_varlen_func`。

**关键坑（两次才跑通）：**
1. 只改 int64→int32 仍崩 `Pipeline run failed: PassManager execution failed`。
2. 定位到 **`ENABLE_I64_CHECK`（镜像 env=1）** 在 gcu300 pass 管线最先跑
   `gcu64-type-verifier`，**静态拒绝 IR 里任何 64 位类型**（`make_gcuir`/compiler.py
   的 gcu300 分支）。`philox_args` 参数无条件是 `!tt.ptr<i64>`（host 传 int64 空张量）
   ——即便 dropout 关闭、philox 永不 deref，指针类型仍在 IR 里 → 被拒。
3. 修法：host 在 `is_dropout=False` 时传 `torch.int32` 的 philox 空张量（注释说明
   GCU300 无 64 位、philox 不 deref）→ verifier 通过。
4. 验证：`ENABLE_I64_CHECK=1`（镜像默认）下，非 paged 与 paged（`block_table` 传入，
   4D `(num_pages, block_size, heads, head_size)` KV）两条路径的 minimal repro 均
   **编译+运行成功**。

**结果：serve 全链路打通，但数值错（attention 输出乱码）**：
- vllm serve（Qwen3-4B TP=8, vendor triton + 全部逐层修复）`Application startup
  complete`，推理返回 32 tokens —— 但输出是**乱码**（如 "话得分ático مض规律…"）。
- minimal 数值对拍：flash 内核 causal=False `max_abs_diff≈2.9`（bf16 应为 ~0.01）；
  对照基本算子 add/silu/mm 在 GCU300 上均正确（max_diff 0 / 4.8e-7 / 3.1e-5）→
  **问题特定于 flash 内核在 GCU300 codegen 上的数值编译**（tl.dot/block-ptr/masked
  softmax 组合中某 pass 误编译），非基础算子、非 int64 门。
- 与 §2.5 iluvatar trap D 同类：**前向数值正确性**，尚未定位到具体 pass。

**待办（决策点）：**
- 调试 GCU300 codegen 对 flash 内核的数值误编译（pass 级定位：pingpong / dot layout /
  fusion / masked softmax）。可能需与 Enflame 工具链团队协作。
- 或评估厂商原生 `flash_attn_gcu` 路径（已能 import；被 empty wheel 缺 `_vllm_fa2_C`
  挡住，见 gcu.py 回退）——若其数值正确，是更短的路。

### int64 阻塞的两层结构（GCU300 无 64 位）

GCU300 triton 拒绝 64 位。**torch_gcu 层没问题**（透明 Long→Int 替换，日志
`GCU not support Long use Int replace`）；**只有落到 triton 内核的 int64 才崩**。
按拦截点分两类，需两套不同修法：

| 层 | 触发者 | 例子 | 修法 |
|---|---|---|---|
| **L1** | flag_gems 拦截的 factory/index 算子（在 torch_gcu Long→Int 之前接管） | `zeros`/`zeros_like`/`zero_`/`add`/`repeat_interleave` | `gcu.yaml` 黑名单 → flag_gems 跳过 → 回退 torch_gcu |
| **L2** | vllm 原生 triton 内核（非 flag_gems） | `_compute_slot_mapping_kernel`（`slot_mapping` 为 int64） | plugin 侧纯 torch 重写，**在 CPU 上算** int64 索引再拷回 device |

### 根因先决 Bug：plugin 配置文件按 vendor_name 找、实际按 device_name 命名

`get_config_path()` 用 `current_platform.vendor_name`（=`enflame`）拼
`enflame.yaml`，但配置文件叫 **`gcu.yaml`**（device_name）。→ **配置从未加载**，
`flagos_blacklist` 与 `op_backends` 全部被静默忽略。这解释了为何最初改黑名单
"无效"。修法：`get_config_path()` 增加 device_name 回退（`gcu.yaml`）。
**同样的坑潜在影响 mthreads**（vendor=mthreads、配置=`musa.yaml`）。

### L1 修复：黑名单 zeros/add/... → 回退 torch_gcu

`gcu.yaml` `flagos_blacklist` 加入 `add / zeros / zeros_like / zero_`（匹配按
函数 `__name__`，而 `zeros` factory 经 torch_gcu wrapper 落到 `zero_`，故 `zero_`
才是必须排除的名字）。配上上面的配置回退，**模型加载阶段的 int64 崩溃清除**。

**三行最小复现（L1）：**
```python
import torch, torch_gcu, flag_gems; flag_gems.enable()
torch.zeros_like(torch.arange(8, device="gcu:0", dtype=torch.int64), device="gcu:0")
# → 64-bit not supported on GCU300（黑名单后回退 torch_gcu 即 OK）
```

### L2 修复：slot_mapping 纯 torch 重写（CPU 计算）

vllm `block_table._compute_slot_mapping_kernel` 在 int64 `positions`/`slot_mapping`
上跑 triton，GCU300 直接拒。plugin 侧 `apply_slot_mapping_gcu_patch()` 把
`BlockTable.compute_slot_mapping` 换成纯 torch 等价实现（含 context-parallel
交织逻辑，已对拍 numpy 参考 **MATCH**）。**关键：必须在 CPU 上算**——若在
device 上算，`flag_gems.enable()` 会把 `repeat_interleave`/`copy` 等再劫持回
int64 triton 内核（又撞同一堵墙）；逐个黑名单既脆弱又会误伤模型热路径计算。
CPU 计算彻底绕开 overlay（flag_gems 只拦 device 算子），数据量极小（每 token
几个 int64），device↔host 拷贝 int64 实测安全。

修完 L1+L2 后：**serve 启动完成**，推理请求进入模型前向，**推进到 attention 层**。

### 阻塞点：attention —— 阻塞 1（flash_attn ABI）已解；阻塞 2（FlagGems int64）为唯一剩余

#### 阻塞 1（✅ 已解除，PR #310 / 2.1.2 镜像）：flash_attn ABI 错配

2.1.1 时 configs.yaml 钉 `flash-attn==2.7.2+torch.2.9.1.gcu.3.4.20260323`：
`flash_attn_gcu.so` 编译于 torch 2.9.1 的 `c10`（3 参 `MessageLogger` ctor），而栈是
torch 2.10.0（4 参 ctor）→ `undefined symbol: c10::MessageLogger`。**PR #310
（`398a00e`）已把钉改为 `flash-attn==2.7.2+torch.2.10.0.gcu.3.4.20260506`**——
厂商已出 torch-2.10.0 的 GCU flash_attn 构建。2.1.2 镜像内 `import flash_attn` /
`flash_attn_gcu` 均正常（§2.6.1 第 1 层）。

#### 阻塞 2（❌ 未解，FlagGems 上游；现正做 GCU 专属 int32 内核）：flash 内核 int64

推理首次前向时崩（§2.6.1 第 7 层）：
`AttentionFLBackend.forward → flag_gems/ops/flash_api.py:579 mha_varlan_fwd →
flash_varlen_fwd_kernel` 用 int64 指针/步长 → GCU300 `make_gcuir` PassManager 拒
（`Pipeline run failed: PassManager execution failed`）。

> **换 triton 前端无用。** int64 拒绝来自 `triton/backends/enflame/compiler.py:233`
> `make_gcuir` 的 PassManager（GCU300 codegen 后端），非前端。FlagTree / 上游
> triton / 任何前端发出的 IR 都要过这一层。绕开只有两条：(a) 内核不落 int64 到
> device（如 L2 的纯 torch 回退）；(b) 内核作者改用 int32 索引。**方向 (b)：为
> enflame/gcu300 提供 int32 索引版的 `flash_varlen_fwd_kernel`（见 §2.6.1 待办）。**

### serve + 推理 —— ⚠️ 2.1.1 阻塞在 attention 两缺口；2.1.2 推进到 flag_gems flash 内核（唯一剩余）

2.1.2 重测（§2.6.1）`Application startup complete` 达成（Qwen3-4B TP=8, vendor
triton + 上述逐层修复），但**推理首次前向**在 `flag_gems flash_varlen_fwd_kernel`
（int64 → GCU300）崩——即 §2.6 记录的 FlagGems int64 阻塞，现已坐实为 attention
通路的**唯一**剩余缺口。修复方向：GCU 专属 int32 索引 flash 内核（§2.6.1 待办）。

### Stack 验证（enflame-tops1.9.10，2.1.2 重测）

```
setuptools:   83.0.0                 ✅  torch_gcu 解钉后稳定（曾被钉 69.5.1）
torch:        2.10.0+cpu             ✅  from 镜像
torch-gcu:    2.10.0+3.7.20260408    ✅
flash_attn:   2.7.2+torch.2.10.0.gcu ✅  PR #310 修复 ABI（原 2.9.1 构建）
numpy:        2.3.5                  ✅
vllm:         0.20.2+flagos          ✅  empty，enflame 本地 build（cp312）
vllm_fl:      g0268a169b             ✅  纯 Python（+ 三处 GCU 修复 + sub 黑名单 + gcu.py attn 回退）
flag_gems:    5.3.2                  ✅  int64 factory/index 算子经黑名单回退 torch_gcu
编译器:        vendor triton(/opt/triton) + TRITON_BACKENDS_IN_TREE=1  ✅  重测时 workaround（PR #332 已根治，见 §2.6.1 双编译器缺口）
GCU device:   ✅ 8 卡可见            arch=dtu-enflame-tops--gcu300
vllm import:  ✅
vllm serve:   ✅  application startup complete（L1+L2 + 2.1.2 逐层修复 + int32 flash 内核）
Inference:    🟡  可返回 tokens，但**输出乱码**——int32 flash 内核编译/运行通过、数值不正确（§2.6.1）
```

### plugin 侧修复（三处 2.1.1 + 两处 2.1.2 重测新增，均容器内验证，PR 待提）

| 修复 | 文件 | 性质 |
|---|---|---|
| `get_config_path()` device_name 回退 | `dispatch/config/utils.py` | 真实潜在 bug（gcu.yaml 从未加载；潜在影响 mthreads/musa.yaml） |
| int64 factory/index 算子黑名单 | `dispatch/config/gcu.yaml` | `add/zeros/zeros_like/zero_` 回退 torch_gcu（2.1.1） |
| slot_mapping 纯 torch（CPU）重写 | `dispatch/backends/vendor/gcu/impl/slot_mapping.py` + `patch.py` | 替换 vllm int64 triton 内核（2.1.1） |
| `sub` 加入黑名单 | `dispatch/config/gcu.yaml` | 2.1.2 重测新增：flag_gems `gcu300/ops/sub.py`（pointwise-dynamic）在 vendor triton 上 make_gcuir 崩（§2.6.1 第 5 层） |
| `attention_backend` 回退 AttentionFLBackend | `dispatch/backends/vendor/gcu/gcu.py` | 2.1.2 重测新增：empty wheel 无 `_vllm_fa2_C` → FLASH_ATTN assert；探测失败回退 flag_gems attn（§2.6.1 第 6 层） |

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| **FlagGems：GCU300 flash 内核 int32 + 数值正确性** | 🟡 半通 | int32 `flash_varlen_fwd_kernel` 已提供并在 GCU300 编译+运行（§2.6.1）；但**数值错**（attention 输出乱码，`max_abs_diff≈2.9`）——GCU300 codegen 对 flash 内核的数值误编译待定位 |
| 厂商为 torch 2.10.0 出 GCU flash_attn | ✅ 已完成 | PR #310（`398a00e`）钉 `torch.2.10.0.gcu.3.4.20260506`；2.1.2 镜像内 flash_attn/flash_attn_gcu 正常 |
| plugin 五处 GCU 修复提 PR | ⬜ 待提 | 容器已验证；对齐 Mac 源码（`gcu.yaml`/`utils.py`/`gcu.py`/`slot_mapping.py`/`patch.py`）后提 |
| 镜像：双编译器隔离（entry-point 泄漏） | ✅ 已解决 | **PR #332**：FlagTree → `/opt/flagtree`、Triton → `/opt/triton` 均出 site-packages；`compiler()` 切 side dir。`TRITON_BACKENDS_IN_TREE=1` workaround 不再需要（§2.6.1 双编译器缺口） |
| 镜像：flash_attn `rotary.py` unguarded `import triton_gcu.triton` | ⬜ 镜像侧/厂商 | 需 triton_gcu 可导入；旧 wheel 有 try/except |
| configs.yaml enflame flash-attn 钉 | ✅ 已对齐 | PR #310 已改 torch-2.10.0 构建；不再与栈错配 |

**相关提交：** 无落库（容器内改动）；empty build 在 enflame 镜像内重新 repack；plugin
修复在容器 `vllm-verify-enflame-212` 的可编辑安装内（Mac 源码待对齐）。2.1.2 重测环境：
Qwen3-4B（ModelScope `Qwen/Qwen3-4B`）、vendor triton + `TRITON_BACKENDS_IN_TREE=1` +
`TORCHDYNAMO_DISABLE=1`。三行复现现场保留。


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
| 厂商 torch 编译的 numpy ABI 与镜像 numpy 不匹配 | 中 | 已遇 iluvatar、hygon（torch 编于 numpy 1.x，镜像 numpy 2.x → `Numpy is not available`）。构建镜像时校验 `torch + tensor.numpy()` 能跑通；厂商 torch 应与 configs.yaml 的 numpy pin 对齐 |

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
| 跨后端正式验证矩阵 | ✅ hygon + iluvatar | 两者均直接复用 mthreads 打的 `+flagos` wheel，单步安装零泄漏（§2.4、§2.5）——两次跨后端实证 |

**若跨后端回归发现 pip 选错版本，备选：** 改用 `0.20.2.post1`（非本地
版本，排序明确高于 `0.20.2`）。

**相关提交：** `main` 478de6b、PR #280（递归 `+flagos` pin，使单步安装成立）。

### 5.2 empty vllm 包的通用性与 wheel 的落点（per-vendor 决策）

empty build 的顶层 vllm 是纯 Python（无硬件代码），repack 只清理 METADATA
依赖声明、不改代码，输出 `py3-none-any`——**vllm 顶层一份 wheel 通用于所有
empty 后端**。compressed-tensors 同理（`py3-none-any`）。

但通用性有粒度：**opencv、xgrammar 是 ABI 绑定的二进制 wheel**——opencv
`cp37-abi3`（稳定 ABI，一份跨所有 CPython≥3.7，仅随 arch 变），xgrammar
`cp310-cp310`（**随 Python 小版本变，也随 arch 变**）。过去 repack 把二进制
wheel 误标成 `py3-none-any`，恰好因 5 个后端都是 cp310 x86_64 而未暴露；一旦
出现 aarch64 或别的 pyver 就会静默装入不可用的 `.so`（§1.3 已修，tag 真实、
pip 按平台选择或明确拒绝）。

> **落点决策：全部 per-vendor，不设 shared `flagos-pypi-hosted`。** 曾设想把
> "通用" wheel 放共享索引省去重复，但 xgrammar 的 per-Python-version 特性会
> 让共享索引要么维护 3×2（pyver×arch）矩阵、要么把安装拆成 hosted+vendor 双
> 索引——后者在 vllm 版本 bump 时尤其脆：`vllm==X+flagos` pin 的 xgrammar 版
> 本若与共享索引里的存货错配，pip 回退到上游 xgrammar，triton 泄漏重现。**留
> 在 per-vendor 则天然规避**：每个 vendor 镜像单一 (python, arch)，
> `build-and-repack.sh <vendor>` 在镜像内跑就产出唯一正确的 opencv/xgrammar
> 变体，与该后端 torch/flag_gems 并列同源；bump vllm 时重跑 repack，整批
> （vllm + 匹配的 xgrammar/opencv/compressed-tensors）同索引原子更新，无跨索引
> 错配。代价仅是 6.7MB 的通用 vllm wheel 在各 vendor 索引各存一份——微不足道。

**已实证（✅ hygon §2.4、iluvatar §2.5）：** mthreads 上打包上传到
`flagos-pypi-mthreads` 的三个 `+flagos` wheel，在 Hygon 与 iluvatar 上原样
单步安装、零 torch/numpy/triton 泄漏（iluvatar 上 wheel 安装本身成功，推理
另因厂商工具链过旧受阻，与 wheel 通用性无关）。技术前提（empty wheel 与
后端无关）成立；剩下的是**上传自动化**，非可行性问题。

**待实现（⬜）：**
1. 扩展 `build-and-repack.sh --upload` 支持批量：对每个 vendor 在其镜像内
   repack + 上传到对应 `flagos-pypi-<vendor>`（纯 Python wheel 可复用，二进制
   wheel 各自 per-(python,arch) 重生）。
2. 或建 on-demand workflow：多 runner（x86_64 + aarch64）分别在各 vendor 镜像
   内 repack → 各传各的 vendor 索引。

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
  **补记（§2.4 修正的前提）：** 最初全局锁的就是 `numpy==1.26.4`，触发
  bump→revert→unpin 的关键推手之一是 `opencv-python-headless 5.0.0.93` 声明
  `numpy>=2`。但该声明是 **faked**——opencv wheel 编于 numpy 2.x、运行时向后
  兼容 1.x，实测 1.26.4 下 C-API 往返完好（§2.4）。也就是说 opencv 从不构成
  真实的 numpy 下限；真正的约束只有"py 版本上限"和"厂商 torch 的 numpy ABI"
  两条。教训：**升级前先分清依赖声明是真实 ABI 约束还是打包策略**——一个
  `import` + C-API 往返测试即可证伪。
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
- **厂商 torch 的 numpy ABI（§2.4）** —— iluvatar、hygon 的厂商 torch 编译于
  numpy 1.x，装到 numpy 2.x 的镜像里 `tensor.numpy()` 直接
  `Numpy is not available`。这不是 repack/vllm 的问题，是镜像里 torch 与
  numpy pin 不配套；教训是**厂商 torch 的 numpy ABI 必须与 configs.yaml 的
  per-backend numpy pin 对齐**，镜像构建时应烟测 `tensor.numpy()`。
