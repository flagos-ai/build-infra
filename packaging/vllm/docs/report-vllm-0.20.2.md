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
| **empty** | 所有后端（NVIDIA 于 2026-08-23 并入） | `VLLM_TARGET_DEVICE=empty` 从源码编译不含硬件 kernel 的 vllm；硬件算子由 vllm-plugin-FL + flag_gems 提供。产物为 `py3-none-any`，纯 Python。 |
| ~~standard~~ | ~~仅 NVIDIA~~ | ~~`pip download` 官方预编译 wheel，含 vllm 自带 CUDA kernel（`_C`）。~~ **已退役（2026-08-23，见 §5.3）** |

> 2026-08-23 起全线统一 empty 模式（"都走统一个模式"），standard 构建退役，
> 决策记录见 §5.3。

## 1.3 Repack

使用 `packaging/vllm/repack.py`（分类规则见 `packaging/vllm/config.yaml`）处理 wheel：

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

- **纯 Python 安装，不设 `VLLM_VENDOR`**（所有后端统一；NVIDIA standard
  编译 C 扩展已退役，2026-08-23，见 §5.3）：`pip install --no-build-isolation .`。
  硬件算子由 plugin 的 dispatch 机制路由到 flag_gems（Triton）。构建产物为
  `py3-none-any` wheel，一份跨后端复用。
- **分支拓扑：** `main` = 0.3.0-dev（vllm 0.24.0 开发线）；0.20.2 支持线在
  **`release-0.2`** 分支，最新 tag **`v0.2.1`**（= commit `825c1cd`）。构建
  0.20.2 线 plugin wheel 必须取 release-0.2（v0.2.1 tag 与该分支 head 同义，
  取哪个都行）。
- **wheel 版本格式：** `{tag}+g{sha}`（PEP 440 local version），如
  `0.2.1+g825c1cd`。app 镜像 tag 中 `+` 转 `_`（workflow 内 `tr '+' '_'`），
  如 `2.1.2-0.2.1_g825c1cd`。

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
| `packaging/vllm/repack.py` | repack 工具：`+flagos` 后缀、Metadata 降级、递归剥离间接依赖 |
| `packaging/vllm/config.yaml` | repack 分类规则（`remove_*` / `strip_from_indirect`） |
| `packaging/vllm/build-and-repack.sh` | 构建（empty/standard）→ repack → `--upload` twine 上传到 vendor PyPI |
| `packaging/vllm/verify-vllm-backend.sh` | 在目标机安装 repacked vllm + plugin，验证 serve/推理 |

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

## 2.1 NVIDIA cuda12.8（参考实现，2026-08-23 起 empty 模式）

**日期:** 2026-07-27/28　**平台:** NVIDIA H20 (8×)
**目标:** vllm 0.20.2 + vllm-plugin-FL，`flagos-runtime-nvidia-cuda12.8:2.1.1`

NVIDIA 是首个跑通的后端，最初使用 **standard 构建**（官方预编译 wheel，含
vllm 自带 CUDA kernel）。2026-08-23 起全线统一 empty 模式，standard 构建
退役（见 §5.3）；本记录保留的历史差异均标注"已被 §1 取代"。这些踩坑正是
标准流程成型的由来（详见 §6）。

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
python3 packaging/vllm/repack.py /tmp/vllm-dl/vllm-0.20.2-*.whl
```

> **历史差异：** 此次 repack 早于 `+flagos` 后缀方案（当时按 §5.1 之前的
> 做法处理版本号）。按 §1.3，今天应统一加 `+flagos`。递归剥离在
> standard 构建下发现的 torch-声明间接依赖比 empty 多（standard wheel 未
> 跳过硬件后端）。

上传（当时手动传 token；今天用 `build-and-repack.sh --upload`）：

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-nvidia/ \
  /tmp/packaging/vllm/output/vllm-0.20.2-*.whl
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
vllm_fl:      loaded        ✅  (plugin wheel 0.2.1+g825c1cd, release-0.2;
                                 旧 standard 期 source build VLLM_VENDOR=cuda 已退役 §5.3)
CUDA:         True          ✅
Inference:    Qwen3.6-35B-A3B ✅  (prompt=17 / completion=128 tokens)
```

### 2026-08-23 复核（empty 模式 + app 镜像 E2E）

§5.3 决策后 NVIDIA 并入 empty 模式。plugin wheel 改从 **release-0.2** 分支
构建（v0.2.1 = `825c1cd`，见 §1.5）：产物
`vllm_plugin_fl-0.2.1+g825c1cd-py3-none-any.whl`（sha256
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
docker run -d --name vllm-app-e2e-nvidia --gpus all \
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
docker run -d --name vllm-app-e2e-triton --gpus all \
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
docker run -d --name vllm-app-e2e-nv133-f --gpus all \
  -v /data/tqm/models:/data/models:ro --network host \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda13.3:2.1.2-0.2.1_g825c1cd
```

- 默认 CMD 即 F 路径（flagtree 默认 active）；约 30 s 就绪；plugin fl 激活。
- `curl /v1/completions` 输出连贯：`Paris. The capital of Paris is...? ...`
  （prompt 5 / completion 32 token）。

**T 路径（triton 3.6.0 side compiler）—— ✅**

```bash
docker run -d --name vllm-app-e2e-nv133-t --gpus all \
  -e PYTHONPATH=/opt/triton \
  -v /data/tqm/models:/data/models:ro --network host \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-nvidia-cuda13.3:2.1.2-0.2.1_g825c1cd
```

- `-e PYTHONPATH=/opt/triton` 显式切到 triton（`compiler` 确认 active =
  triton 3.6.0）；约 30 s 就绪；同一 prompt 输出连贯。两容器验证后均已清理。

### 待办

1. ~~扩展到 nvidia-cuda13.3（相同模式，torch 2.11.0+cu130）~~ —— ✅ 2026-08-23
   （见上文 cuda13.3 复核记录）。
1. ~~empty-mode 性能基准~~ —— §5.3 已定案全线统一 empty（2026-08-23），
   基准不再门控；empty 下 NVIDIA 性能实证见 0.24.0 报告（Qwen3-4B E2E）。
1. NVIDIA empty 模式 app 镜像 E2E —— ✅ 2026-08-23（见上文复核记录）。

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
python3 packaging/vllm/repack.py /tmp/empty/vllm-0.20.2+empty-*.whl
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
  flagtree==3.1.0+metax3.7.2.0 triton==3.0.0+metax3.7.2.0 flag_gems==5.3.4 \
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
flag_gems:    5.3.4                 ✅
vllm:         0.20.2                ✅  empty, repacked, vendor PyPI
vllm_fl:      installed             ✅  纯 Python + #333
MACA device:  ✅ 可见                mx-smi (C550 8×64GB)
vllm serve:   ✅ 启动成功            TP=1, enforce-eager, gpu-util 0.6
Inference:    ✅ 成功                Qwen3-4B, prompt=5 / completion=16
```

### Triton 路径（T）复验：flag_gems scalar 返回 bug（2026-08-25）

**运行时镜像:** `flagos-runtime-metax-maca3.7.2.1:2.1.2`（flag_gems 5.3.4）。
maca3.7.2.1-T 在 `vllm serve` 阶段崩溃，报 `EngineCore` 初始化失败（v1 引擎
吞掉真实子进程 traceback）。根因在 flag_gems `LibTuner` 与 triton 3.0.0
的基准接口不匹配，两层：

1. triton 3.0.0 的 `Autotuner._bench` 在 `use_cuda_graph=True` 时走
   `do_bench_cudagraph(..., return_mode="median")`，返回**标量** median，
   而非标准的 `(p50, p20, p80)` 三元组。
2. flag_gems `LibTuner` 默认 `benchmark_mode=REPLAY`，triton 3.0.x 分支跳过
   `resolve_benchmarker`，`super().__init__` 拿到 `use_cuda_graph=True`；
   其 `bench` 闭包 `for value in ret` 迭代标量 → `TypeError: 'float' object
   is not iterable`（libentry.py:997）。
3. 即使把标量包成单元素 list，flagtune BenchmarkCache v2 按 3 分位数存取
   （sql.py `p50, p20, p80 = benchmark`）→ `ValueError: not enough values to
   unpack (expected 3, got 1)`。

**修复（上游 FlagGems `1537bde93a8e` / PR #5375）：** 在 `bench` 闭包把标量
归一化为 `(ret, ret, ret)`，`benchmark_with_requested_quantiles` 同步归一化
（`isinstance(ret, (int, float))`）。该修复**不在**任何 ≤ v5.3.4 的 tag，
已进入每日构建 `5.3.5.dev20260825`（下载 wheel 确认含归一化代码）。

**验证（2026-08-25）：** 本地补丁 triton 3.0.x legacy 分支
`use_cuda_graph=False`（等效于上游归一化，让 `_bench` 走 `do_bench` 返回
三元组）后，`vllm serve` 稳定到 `serve_ready`（~145s），真实
`POST /v1/completions` 返回 `200 OK` —— T 路径 E2E 通过。**但这是补丁验证，
runtime 镜像（flag_gems 5.3.4）尚未含修复，见待办。**

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| plugin-FL #333 | ✅ 已提，E2E 通过 | `reshape_and_cache_flash`→flag_gems（`CachedOp`） |
| plugin-FL #319 | ✅ 已关闭 | 守卫恒真从不生效，被 #333 取代 |
| plugin-FL #325（`_maca`→F.silu/F.gelu）| ✅ 已关闭 | empty wheel 上 dispatch 不走 vendor 路径，实测不需要（仅 +cpu wheel 有意义） |
| repack.py empty 支持 + 递归审计 | ✅ | PR #244 #247 |
| 更大模型 / graph / TP>1 | ⬜ | 仅测过 Qwen3-4B + eager |
| FlagGems pyproject build-system.requires 加 `wheel==0.45.0` | ⬜ | |
| flag_gems scalar 返回 bug 固化 | ⬜ | 上游 `1537bde93a8e` 已修；运行时仍 pin 5.3.4，需决定 bump 到含修复构建 vs 容器补丁 |

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
./packaging/vllm/build-and-repack.sh mthreads-musa5.2.0 --upload
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

### app image 验证 —— 双后端 F/T 全通（2026-08-24）

这是 vllm 0.20.2 在 mthreads 上的最终交付形态——不再是本节早前的手工容器
安装，而是两个后端各自构建并 push 的 app image（`vllm==0.20.2+flagos` 单步
装入 + `vllm-plugin-fl` wheel + `vllm-serve` launcher），stack 2.1.2：

| 后端 | app image tag | 硬件 |
|------|------|------|
| mthreads-musa4.3.6 | `vllm0.20.2-mthreads-musa4.3.6:2.1.2-0.2.1` | MTT S5000 |
| mthreads-musa5.2.0 | `vllm0.20.2-mthreads-musa5.2.0:2.1.2-0.2.1` | MTT S5000 |

F（FlagTree）/ T（Triton）双路径均 E2E 通过（Qwen3-4B，`--enforce-eager
--max-model-len 2048`），四格全 ✅。

关键包版本：

| 包 | musa4.3.6 | musa5.2.0 |
|------|------|------|
| torch | 2.9.0+musa.4.3.6 | 2.9.1+musa5.2.0 |
| torch_musa | 2.9.0 | 2.9.1 |
| triton | 3.6.0+git89458660 | 3.6.0 |
| flagtree | 0.6.1+mthreads3.6 | 0.6.1+mthreads3.6 |
| flag_gems | 5.3.4 | 5.3.4 |
| numpy | 1.26.4 | 1.26.4 |
| vllm | 0.20.2+flagos | 0.20.2+flagos |
| vllm-plugin-fl | 0.2.1 | 0.2.1 |

三处与前文记录不同：

1. **triton 并非不存在。** 早前 Stack 验证写 `triton: (absent)`，那是
   runtime 2.1.1 的旧状态。2.1.2 起 triton 3.6.0 作为 side install 落在
   `/opt/triton`，不在默认 `PYTHONPATH`（默认是 flagtree）；`compiler
   triton` 切换后即可 import + serve。`importlib.metadata` 只见当前激活
   编译器——app-image 快照比对里 triton 报 `NOT_INSTALLED` 即此故，非缺失。
2. **模型路径。** 节点实际模型在 `/datapool/models/Qwen3-4B`
   （`/data/models` 为空）。
3. **必须带 `--runtime mthreads`。** 不带则 `import vllm_fl` 报
   `0 active drivers`（无设备访问）。

serve 配方（每路径一个端口，先 `compiler <c>` 切编译器）：

```bash
docker run -d --name vllm-verify-musa520 \
  --runtime mthreads --env MTHREADS_VISIBLE_DEVICES=2 \
  --network host -v /datapool/models:/datapool/models \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-mthreads-musa5.2.0:2.1.2-0.2.1 \
  sleep infinity
docker exec vllm-verify-musa520 bash -lc "
  compiler triton
  export VLLM_PLUGINS=fl VLLM_FL_DISPATCH_DEBUG=1
  vllm serve /datapool/models/Qwen3-4B --port 8034 --enforce-eager \
    --max-model-len 2048 --gpu-memory-utilization 0.6 --trust-remote-code &
"
```

四条 serve 的 completion 一致输出 "Paris. The capital of Germany is
Berlin..."，health endpoint 均 200。

**mul 门控（#5130）已在镜像内。** flag_gems 5.3.4 自带
[#5130](https://github.com/flagos-ai/FlagGems/pull/5130) 修复，无需再手工
打 patch——早前本节的临时补丁到此收敛为制品。

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

## 2.6 enflame（GCU300：✅ E2E 通过，vLLM 原生 FLASH_ATTN，跨栈收敛）

**方案:** vLLM 原生 FLASH_ATTN + 五处修复（plugin A/B/C/E [PR #357](https://github.com/flagos-ai/vllm-plugin-FL/pull/357) + flag_gems D [PR #5345](https://github.com/flagos-ai/FlagGems/pull/5345)）。
**跨栈收敛（关键结论）:** 同一份代码在 **tops1.10.6**（torch_gcu 2.11，首次推导 2026-08-09）
与 **tops1.9.10**（torch_gcu 2.10.0，复验 2026-08-09）上**零改动**通过 E2E——不再是每栈一个
方案。此前 1.9.10 上的 `AttentionFLBackend` 记录（旧 §2.6.1）已删除：其诊断（int64 双层结构、
采样根因）已被本节 + `enflame-1910-reval.md` 覆盖，且被更贴近上游的原生 FLASH_ATTN 路径取代。

> **约束提醒（贯穿两栈）：** GCU300 的 triton 后端（`make_gcuir` 的 PassManager）彻底拒绝
> 64 位数据类型——不是前端 / FlagTree 问题，换 triton 前端无用，拒绝发生在 GCU300 codegen
> 后端。五处修复中 A/D/E 都是绕这堵 64 位墙。

### 2.6.1 tops1.10.6 干净重推导（✅ E2E 通过，2026-08-09）—— 首次推导

**日期:** 2026-08-09　**平台:** Enflame GCU300　**节点:** `enflame1`
**镜像:** `flagos-runtime-enflame-tops1.10.6:2.1.2`　**容器:** `vllm-verify-fresh`
**stack:** torch_gcu 2.11 / tops1.10.6 / **flag_gems master（editable）** / plugin main（editable）

从零容器起、不预置任何补丁，逐个由硬件暴露的失败驱动修复。采用 **vLLM 原生 FLASH_ATTN**
（干净 plugin main 已改用该路径——更贴近上游、用厂商快内核）：原生后端需要把厂商 flash_attn
的计算算子与 flag_gems 的 KV 写内核接进 vLLM。此方案已提 PR（#357 / #5345），并在 1.9.10 栈上
复验通过（见 §2.6.2），确认跨栈收敛。

#### 五处修复（均在 git 可追踪的 editable flag_gems / plugin 内，vLLM site-packages 保持原样）

| # | 缺口 | 家 |
|---|---|---|
| A | 模型加载期 flag_gems int64 工厂/索引算子（`zeros`/`add`/`sub`…）触 GCU300 64 位墙 | plugin 配置 `enflame.yaml`：黑名单回退 torch_gcu |
| B | `FlashAttention version not detected`（空 wheel 无 `_vllm_fa2_C`） | plugin `__init__.py`：早期把厂商 `flash_attn.vllm_flash_attn` 别名到 `vllm.vllm_flash_attn` |
| C | `reshape_and_cache_flash` NameError（empty build 剥离 `vllm._C`） | plugin `gcu/impl/flash_attn_backend.py`：把厂商 FA 计算 + flag_gems KV 内核绑上 `fa_utils` |
| D | flag_gems `reshape_and_cache_flash` 内核收 int64 `slot_mapping` | flag_gems `fused/reshape_and_cache_flash.py`：降位 int32 |
| E | vLLM 原生 `_compute_slot_mapping_kernel` 内建 int64 | plugin `gcu/impl/slot_mapping.py`：纯 torch on-device int32 重写 |

#### 设计取舍

**B/C 为何是插件层、且 vLLM 保持原样。** 两者都可直接改 vLLM `fa_utils.py`，但那是 empty
build 的 wheel，站点包手改不可复现。改为在 `apply_gcu_patches()`（GCU 后端加载时运行）里
绑定：C 把厂商 `flash_attn_varlen_func`/`get_scheduler_metadata` 与 flag_gems
`reshape_and_cache_flash` 绑上 `fa_utils` 并强制 `is_flash_attn_varlen_func_available()`→True。
补丁对导入顺序稳健——若 `flash_attn.py` 已先导入（其加载期条件导入已跳过这些名字），则同时
把这些名字注入该模块命名空间。全程以 `torch_gcu` 存在为门（enflame 专属），厂商无 flash_attn
包时静默回退、不影响其他后端。

**D/E 都要、且不冗余。** E 重写 `slot_mapping` 的**生成**（vLLM 原生内核），D 降位
`slot_mapping` 的**消费**处（flag_gems KV 写内核）。vLLM 的 `slot_mapping.gpu` 缓冲区 dtype
为 int64，E 产出的仍是 int64，故 D 在消费端的降位仍然必要。A 覆盖的是加载期的 L1 工厂/索引
算子，早于任何注意力路径，独立于 D/E。

**E 采用 on-device int32 而非 CPU-int64。** 缓存槽位空间（`num_blocks * block_size`，现实
配置 ~1e8）远在 int32 上限（~2.1e9）内，全程 int32 可绕开 64 位墙又无 host round-trip。
token→request 映射用 `torch.searchsorted(qsl[1:], tok, right=True)`，而非
`repeat_interleave`——后者在 GCU300 flag_gems 走 index_select 内核，grid.y 上限 255，超
~4080 token 即崩。落库前用 CPU-int64 参考对拍 5 组用例（含 4096 token、max_slot ~2.08M），
逐元素 bit-identical。

#### Stack 验证（enflame-tops1.10.6，✅ E2E 通过 2026-08-09）

```
vllm:         0.20.2+flagos           ✅  empty，enflame 本地 build（cp312），site-packages 原样
vllm_fl:      main f4ebc258 (editable) ✅  A 配置改名 + B FA 别名 + C FA/KV 绑定 + E slot_mapping 重写（PR #357）
flag_gems:    master 469bb00d (editable)✅  D reshape_and_cache_flash slot_mapping int32（PR #5345）
torch_gcu:    2.11                    ✅  透明 Long→Int（torch 层无 64 位问题）
GCU device:   ✅ 可见
推理:         Qwen3-4B → "Paris"      ✅  连贯英文，20→64 token，finish_reason=length，HTTP 200 9.2s
```

**环境：** vendor triton（`compiler triton`）+ `VLLM_PLUGINS=fl`，Qwen3-4B TP=1 max-len 4096
enforce-eager，`/root/run_serve.sh` 现场保留。两处插件 patch 日志（主进程 + worker）均出现：
`enabled native FLASH_ATTN backend` 与 `patched BlockTable.compute_slot_mapping (on-device int32)`。
完整变更记于 `enflame-1106-fresh-verify.md`。

### 2.6.2 tops1.9.10 跨栈复验（✅ E2E 通过，2026-08-09）—— 零改动 + 采样缺口修复

**日期:** 2026-08-09　**平台:** Enflame GCU300　**节点:** `enflame1`
**镜像:** `flagos-runtime-enflame-tops1.9.10:2.1.2`（runtime v2：仅预置 flag_gems，**无 vllm、无 plugin**）
**容器:** `vllm-verify-1910`　**stack:** torch_gcu **2.10.0** / tops1.9.10 / flag_gems master（editable）/ plugin #357（editable）

在 1.9.10 栈全新 v2 容器上复验 §2.6.1 方案，判定是否可退役 1.9.10 上的 AttentionFLBackend。
纪律：vllm 从厂商 index 单步装（`vllm==0.20.2+flagos`，非磁盘捞取），flag_gems / plugin 走
上游 PR 树 editable，无手改。**环境变量策略：** 仅显式 `compiler triton`（flagtree 不信任，
故明确选 vendor triton），不设任何其他环境变量——`VLLM_PLUGINS=fl` 经确认冗余（plugin 靠
entry point 自动发现）。完整记录见 `enflame-1910-reval.md`。

**结论 1 —— 贪心零改动通过（跨栈收敛坐实）：**

```
vllm:         0.20.2+flagos（vendor index 单步装）   ✅  site-packages 原样
vllm_fl:      #357 分支 6e35613 (editable)            ✅  A/B/C/E 全部生效
flag_gems:    master 3f5fb04 (editable, Fix D 已合并)  ✅  D
torch_gcu:    2.10.0                                  ✅  vs 1.10.6 的 2.11，无需代码差异
compiler:     vendor triton（compiler triton）        ✅  显式，flagtree 不信任
推理:         Qwen3-4B, greedy → 连贯英文             ✅  "…Paris is the capital"，HTTP 200，27.8s
```

五处修复跨 torch_gcu 2.11 → 2.10.0 **全部零改动移植**，唯一磕绊是环境性的（残留兄弟容器占住
GCU 0 显存，`docker rm -f` 解决），非代码缺口。

**结论 2 —— 采样（temp>0）缺口：贪心 E2E 看不见的真实洞，已修（配置层）：**

贪心走 `argmax`，不触发 top-k/top-p sort 路径。显式测采样（`temp=0.8, top_p=0.9`）逐个由
硬件失败驱动、增量补 GCU300 dispatch 黑名单（每个 op 都由一次现场失败换来，非照搬旧笔记）：

| 加入 `enflame.yaml` 黑名单的 op | 修复的症状 | 类型 |
|---|---|---|
| `sort`, `sort_stable` | 崩溃：`logits.sort()` → gcu300 radix_sort int64 → PassManager 拒绝 | int64 墙 |
| `rsub_scalar`, `rsub_tensor` | 崩溃：top-k `logits_sort.size(1) - k` → rsub int64 → 同墙 | int64 墙 |
| `argmax` | 退化输出（空/纯空白，不崩溃）：flag_gems gcu300 argmax 大词表下返回越界 token id；torch_gcu argmax 正确 | correctness |

修复为纯配置（路由到 torch_gcu），enflame 专属。补齐后 `temp=0.8/top_p=0.9` 在 Qwen3-4B 上
输出连贯（两个 prompt 确认）。未加密（`q.exponential_()`）经探针确认在 GCU300 上正确，无需
黑名单。**已推 #357（commit 851bbda）。**

**结论 3 —— flag_gems gcu300 argmax 是真实内核 bug（根因已定，非 `and`/`&`）：**

追到根因：`argmax.py:103` 的 `and`→`&` 反模式**不是**修复——改后清全部缓存、debug log 确认
补丁内核确实执行，仍返回越界 id。探针刻画：词表门槛（V≤32768 对、V=151936 错，需多 tile
`BLOCK_N` 循环）+ 偶数行奇偶性（B=8 行 0/2/4/6 错、1/3/5/7 对），错值是最后一个 tile 的被
mask lane。**根因：GCU300 triton_gcu 跨 tile 归约累加的 codegen 误编译（偶数 lane 奇偶性）。**
`and`-on-tensor 反模式确实广泛存在（~50 处 / ~20 个 gcu300 算子）但修它不改 argmax 行为，两
件事分开。已生成面向厂商的中文根因报告 `flaggems-gcu300-argmax-bug.md`。已验证的生产修复仍是
黑名单（argmax → torch_gcu，已在 #357）。

#### 待办 / 落库

- **本节为 enflame GCU300 唯一主路径，跨栈收敛已坐实**（1.10.6 + 1.9.10 同一份代码零改动通过）。
  旧 §2.6.1（1.9.10 AttentionFLBackend 历史记录）已删除，诊断内容并入 `enflame-1910-reval.md`。
- **已落库**：五处修复 + 采样黑名单已提 PR（均直推 flagos-ai）：
  - **plugin（A/B/C/E + 采样黑名单）→ [PR #357](https://github.com/flagos-ai/vllm-plugin-FL/pull/357)**：分支 `enflame-gcu300-native-flash-attn` → `main`。走 vLLM 原生 FLASH_ATTN。**注：** slot_mapping / fa_utils 绑定耦合 vLLM v1 worker/attention 布局，须对齐 vLLM 0.24.0 迁移后重新推导。
  - **flag_gems（D）→ [PR #5345](https://github.com/flagos-ai/FlagGems/pull/5345)**：分支 `enflame-gcu300-reshape-cache-int32` → `master`。vendor+dtype gated 的 slot_mapping int32 降位，与 vLLM 版本解耦。
- **flag_gems gcu300 argmax codegen bug** → 中文厂商报告 `flaggems-gcu300-argmax-bug.md`，待发厂商 triton_gcu 团队；修复后可从 #357 黑名单移除 `argmax`。
- 仅测单轮 64 token 生成；多轮 / 长上下文未验。
- 加密采样（`exponential_(generator=)`）未测。
- E 的 CP>1 交织分支已实现但未测（本配置 cp_world=1）。
- 运维备忘：teardown 需一并 `pkill -9 -f "EngineCore"`——spawn worker 不匹配
  `[v]llm serve`，残留会占住 GCU 显存致下次启动 OOM；已完结的验证容器也需 `docker rm -f`。

---

## 2.7 cambricon-neuware4.7.2（MLU590：✅ E2E 通过，2026-08-08；2026-08-15 复核）

**日期:** 2026-08-08（初验）；2026-08-15（复核，empty 黑名单删除 + index 回归）
　**平台:** Cambricon MLU590　**节点:** `cambricon`
**driver/neuware:** 4.7.2　**镜像:** `flagos-runtime-cambricon-neuware4.7.2:2.1.2`（`1a2a53ebab3b`，全量升级包集）
**容器:** `vllm-verify-camb472`　**Python:** 3.12.13　**torch/torch_mlu:** 2.11.0+cpu / torch_mlu 2.11.0
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，全新 wheel build（cambricon 此前无 `+flagos` 产物）
**模型:** Qwen3-8B（`/data/zhaodeming/Qwen3-8B`）

cambricon 是**首个从零构建 `+flagos` wheel 的后端**（无可复用产物），故本次同时是
cambricon 的 wheel-build 首验。全链路 **serve + 推理一次跑通**，MLU590 上 Qwen3-8B
贪婪解码输出连贯英语，无数值 / 乱码问题。

### Repack —— 在 cambricon 上从零 build（cp312，源码用官方 flagos tarball）

MLU 无既有 `+flagos` 产物；xgrammar 为 cp312-locked 二进制，须本机 build。步骤：

1. **源码用官方 flagos tarball**（`vllm-0.20.2.tar.gz`，用户下载到节点 `/tmp`），
   **非** Aliyun pip sdist。tarball 无 git 元数据，setuptools-scm 会失败 →
   须设 `SETUPTOOLS_SCM_PRETEND_VERSION=0.20.2`。
2. empty build：`VLLM_TARGET_DEVICE=empty MAX_JOBS=$(nproc) pip wheel --no-build-isolation --no-deps`
   → `vllm-0.20.2-py3-none-any.whl`，`repack.py` 打 `+flagos` 后缀并递归 repack 间接依赖。
3. repack 需预建缓存目录：`mkdir -p <repack>/cache`（否则 `_download_dep_wheel` 报
   `FileNotFoundError: cache/...whl`）。

产物 4 个 wheel（vllm、xgrammar **cp312**、compressed-tensors、opencv-headless）。

### 安装 —— ✅ 单步，零泄漏

`flagos.net` 存储故障期间走本地 wheel + Aliyun extra-index 单步安装，实测零泄漏：

```
vllm:                   0.20.2+flagos          ✅  empty，cambricon 本地 build（cp312）
xgrammar:               0.2.3+flagos           ✅  cp312-cp312（per-Python 二进制）
compressed-tensors:     0.15.0.1+flagos        ✅  纯 py3
opencv-python-headless: 5.0.0.93+flagos        ✅  cp37-abi3（稳定 ABI）
torch / torch_mlu:      2.11.0+cpu / 2.11.0    ✅  from 镜像，无公有 torch/cuda/triton 链
```

无 pip 冲突，无 setuptools 降级（不同于 enflame）。

### 插件 —— ✅ 干净安装（--no-build-isolation，纯 Python）

`pip install --no-build-isolation -e .`，`VLLM_VENDOR` 未设 → 纯 `py3-none-any`
（`vllm-plugin-fl 0.2.0`）。无 enflame 的 setuptools 钉阻塞。

### serve + 推理 —— ✅ 成功（3 处 plugin patch + 1 处 flag_gems 黑名单 + 1 次算力清理）

MLU590 上带起 serve 需 4 个修复。前 3 个是 plugin 未覆盖 cambricon 的缺口，第 4 个是
flag_gems `empty` 内核在 MLU 上撞 triton grid 上限：

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 1 | `Vendor 'cambricon' not found in VENDOR_DEVICE_MAP`（`utils.py`） | `VENDOR_DEVICE_MAP` 无 cambricon 条目，`_get_vendor_device_field` 抛 ValueError | `utils.py:53` 加 `"cambricon": {"device_type": "mlu", "device_name": "mlu"}` |
| 2 | `NotImplementedError: not support graph`（`compilation/graph.py`） | `Graph` 类无 mlu 分支 | `graph.py:52-53` 加 `elif current_platform.device_type == "mlu": graph = torch.mlu.MLUGraph` |
| 3 | `OutOfResources: grid size 607744 > 65535`（`flag_gems/ops/empty.py:87`） | flag_gems `empty` 内核对 Qwen3 词表 embedding（151936×4096）算出 grid 607744，超 MLU triton grid 上限 65535 | 黑名单 `empty`。**定稿走 plugin 内建配置 `dispatch/config/cambricon.yaml`（Priority 3），非 env**：文件名须匹配 `current_platform.vendor_name`（`cambricon`）才被 `get_config_path()` 自动加载。已容器验证：不设 `VLLM_FL_FLAGOS_BLACKLIST` 时 `use_flaggems_op('empty')=False`、serve 启动完成、推理连贯（隔离测试另证 `flag_gems.enable(unused=)` 键是 `empty` 而非 registry 名 `empty.memory_format`） |
| 4 | 内存不足（62.68 GiB free < 67 GiB） | 前次崩溃留下孤儿 `VLLM::EngineCore` 进程占住 MLU0 约 16.5 GiB | 清理孤儿进程 + `MLU_VISIBLE_DEVICES=0` 单卡 |

修复后 serve 启动：`init engine (profile, create kv cache, warmup model) took 406.84 s
(compilation: 96.79 s)`，KV cache 350,240 tokens，`Application startup complete`。

**首次推理**首 token 延迟高（首请求逐 shape 编译 triton 内核，60s curl 超时；加长到
300s 即返回）；`_cambricon/ops/mean.py` 等 flag_gems cambricon 算子活跃，无错。

### 2026-08-15 复核（2.1.2 镜像 / flag_gems 5.3.4）：empty 黑名单可删 ✅，index op 回归 → flag_gems 根因修复

**empty ✅（黑名单已删，无回归）：** 2.1.2 镜像装 flag_gems **5.3.4**（已含
cambricon 专属 `_cambricon/ops/empty.py` 分块修复，PR #4435）。将 `cambricon.yaml`
的 `flagos_blacklist` 清空为 `[]` 实测：serve 启动完成、推理连贯 → **`empty` 黑名单
可安全删除**（这正是 §2.7 初验时"根治 = 升 flag_gems 到含 #4435 的版本"的兑现）。

**index op 回归（E2E 确定性崩溃，黑名单已加）：** 复核过程中首次请求即触发 flag_gems
cambricon `index` op 在 **flagtune 自动调参 bench** 阶段崩溃，EngineCore 直接死亡
（HTTP 500 / EngineDeadError）。复现路径与完整证据链：

- **触发点：** `model_runner.py:4145` `sample_hidden_states = hidden_states[logits_indices]`
  → `_cambricon/ops/index.py` `_index_func`（461）→ code_cache `_index_wrapper` → triton autotune。
- **崩溃：** Triton MLU 后端 `compiler.py:722` `make_optimized_linalg` 的
  `PassManager::run` 抛 `RuntimeError: PassManager::run failed`，原始 MLIR 报
  `'tensor.expand_shape' op expected dimension 0 of collapsed type to be static value of 4`
  （`AutoTileForTritonPass`，发生在 `genesis.num_stages = 2`、`linalg_ext.scatter`、
  `tensor.extract_slice [4, %76]`、`tensor.expand_shape %81 [[0,1],[2]] output_shape [1,4,4096]`
  的 bench 阶段，shape (15, 4096)、BLOCK_SIZE0=4 / BLOCK_SIZE1=4096、num_warps 4）。
- **为什么 autotuner 救不了：** RuntimeError 在 triton `autotuner.py:160` `_bench` 内抛出，
  但**不在** triton 的 `(OutOfResources, CompileTimeAssertionFailure, PTXASError)` catch 列表
  → 无法转 `inf` 跳过该 config → 直接传播 → EngineCore 死。
- **与 DB 中 inf 行的关系（已厘清，二者无关）：** `TunedConfig_cambricon_triton_3_4.db`
  (15, 4096) 的 inf 行是 **ns=2 + b1=4096 的 NRAM 超限**（nw=4: 609024 / nw=1: 856400 >
  MLU590 硬件上限 524288 → OutOfResources → 被 tuner 正确捕获记 inf），18 个 bench config
  中其余 16 个 standalone 全部 PASS。expand_shape 崩溃是 **E2E 上下文专属**（inductor wrap +
  BACKED dynamic shapes + VLLM_COMPILE=3），standalone 不触发。
- **修复（两处，E2E 已验证）：** ① 过渡：`vllm_fl/dispatch/config/cambricon.yaml`
  `flagos_blacklist: [index]`（与 `empty` 同机制：Priority 3 内建配置，回退 torch_mlu）。
  ② 根因：**flag_gems PR #5510**（libentry `bench()` 将任意 `RuntimeError` 视为 inf
  非候选，防后端编译 bug 杀进程；`_cambricon/tune_configs.yaml` index 块删
  `BLOCK_SIZE1=4096`——该 config 是崩溃触发者，且 ns=2 下 4096 宽 tile 恒超 NRAM
  本就不能赢）。**实测：** 去掉黑名单（`flagos_blacklist: []`）重启 serve 后，原崩溃
  请求 200 返回正确输出，连续请求 EngineCore 存活、0 ERROR。黑名单在 #5510 随
  flag_gems 发布前保留作过渡。
- **遗留：** 原始 MLIR reproducer 已留存（容器 `/tmp/serve534_crash_index2.log`）。厂商
  hand-off 文档（flag_gems/MLU Triton AutoTileForTritonPass expand_shape bug）待整理。



### Stack 验证（cambricon-neuware4.7.2，✅ E2E 通过 2026-08-08）

```
setuptools:   稳定（无降级）           ✅
torch/torch_mlu: 2.11.0+cpu / 2.11.0  ✅  from 镜像
vllm:         0.20.2+flagos          ✅  empty，cambricon 本地 build（cp312）
vllm_fl:      0.2.0 + 3 patch        ✅  纯 Python（VENDOR_DEVICE_MAP / MLUGraph / —）
flag_gems:    5.3.4（empty 分块修复已含，见 PR #4435）  ✅  empty 黑名单已删；
                                          index 根因修复已提 PR #5510（libentry 防护 +
                                          删 b1=4096 调参项）；黑名单为过渡（发布前保留）
MLU device:   ✅ MLU0 单卡           MLU590
vllm import:  ✅
vllm serve:   ✅  application startup complete（Qwen3-8B TP=1, max-len 4096, mem-util 0.85）
Inference:    ✅  连贯英语——"What is the capital of France?" → 正确推理至 Paris；
                  finish_reason=length（64 token 上限），无乱码/dtype/libdevice 错
                  POST /v1/chat/completions 200 OK，生成 ~4.3 tokens/s
```

### plugin 侧修复（3 处代码 + 2 次黑名单演进，均容器内验证，已入 PR #355）

| 修复 | 文件 | 性质 |
|---|---|---|
| `VENDOR_DEVICE_MAP` 加 cambricon → mlu | `vllm_fl/utils.py:53` | plugin 未覆盖 cambricon（真实缺口） |
| `Graph` 加 mlu → `torch.mlu.MLUGraph` 分支 | `vllm_fl/compilation/graph.py:52` | plugin `Graph` 无 mlu 分支（真实缺口） |
| 黑名单 `index`（内建配置；`empty` 已随 5.3.4 修复移除） | `dispatch/config/cambricon.yaml` `flagos_blacklist: [index]` | `index` op flagtune bench 时 expand_shape/AutoTileForTritonPass 崩溃（见 2026-08-15 复核）；回退 torch_mlu。**过渡**：根因已修 flag_gems PR #5510，发布前保留。`empty` 同机制黑名单于初验加入、5.3.4（PR #4435）落地后删除。定稿走 plugin 内建配置（非 env），文件名匹配 vendor_name=`cambricon` 才自动加载 |

本地补丁副本：`/tmp/camb-patches/{utils.py,graph.py}`。serve 脚本：
`/tmp/camb_serve6.sh`（复核用 `/tmp/launch_serve534.sh`，日志 `/tmp/serve534.log`）。

### MLU590 约束记录

- **triton grid 上限 65535**（vs NV 2^31-1）：任何按元素总数算 grid 的 flag_gems
  内核在大张量上都会撞（本次为 `empty`；其它大算子潜在同类风险）。
- **num_warps 上限 4**：超出触发 fallback warning（非致命，仅噪声）。
- `torch.mlu.MLUGraph` 存在（对应 CUDAGraph），plugin graph 分支可直接用。

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| 3 处修复对齐 Mac 源码并提 PR | ✅ 已提 | **PR #355**（flagos-ai/vllm-plugin-FL）：VENDOR_DEVICE_MAP cambricon→mlu + graph.py mlu→MLUGraph（2 处代码，通用缺口非 cambricon hack）+ `dispatch/config/cambricon.yaml`（内建配置非 env）。三处全部 E2E 验证 |
| `empty` 黑名单固化 → 2026-08-15 已随 5.3.4 移除 | ✅ 已入 PR #355 | 初验定稿为内建配置 `dispatch/config/cambricon.yaml`（非 env）。5.3.4 含 #4435 分块修复后，复核实测 `flagos_blacklist: []` serve + 推理正常 → PR 已删 `empty` 黑名单 |
| `index` op 崩溃根因修复 | ✅ 已提 flag_gems PR #5510 | 两处：libentry `bench()` RuntimeError→inf 防护 + `_cambricon` index 调参删 `BLOCK_SIZE1=4096`。去黑名单 E2E 实测通过（首请求 200、EngineCore 存活）。发布前 plugin 黑名单保留作过渡 |
| flag_gems `empty` MLU grid 分块 | ✅ 上游已修，已进 5.3.4 | **PR #4435**（2026-08-07 合入 master）cambricon 专属 `_cambricon/ops/empty.py`（grid 上限 `TOTAL_CORE_NUM` + grid-stride 循环 + int64 offset）。5.3.3 发布早于 #4435 故不含；2.1.2 镜像装 5.3.4 已含 → `empty` 黑名单删除且实测无回归 |
| cambricon `+flagos` wheel 上架 per-vendor index | ✅ 已上传 | 4 个 wheel（vllm / xgrammar cp312 / compressed-tensors / opencv-headless）已上架 `flagos-pypi-cambricon`；不再依赖本地 wheel |
| index expand_shape / AutoTileForTritonPass 厂商 hand-off | ⬜ 待整理 | flag_gems/MLU Triton 编译 bug（libentry 防护已绕开）；reproducer 已留存 `/tmp/serve534_crash_index2.log`，文档待补 |

**相关提交：** 2026-08-15 复核后 **PR #355 分支已更新**（`5dd5f7b`，仅 cambricon.yaml：
删 `empty` 黑名单、加 `index` 黑名单）。**根因修复 = flag_gems PR #5510**
（`fix/cambricon-index-expand-shape`：libentry RuntimeError 防护 + 删 `BLOCK_SIZE1=4096`），
去黑名单 E2E 验证通过；PR #355 的 `index` 黑名单保留为过渡，待 #5510 随 flag_gems
发布后删除。wheel 在 cambricon 镜像内从官方 tarball 重新 build + repack。


---

## 2.8 ascend-cann9.0.0（Ascend 910B4 aarch64：✅ E2E 通过，2026-08-10）

**日期:** 2026-08-10　**平台:** Ascend 910B4（aarch64）　**节点:** `hw25`
**driver/CANN:** npu-smi 26.0.rc1 / CANN 9.0.0　**镜像:** `flagos-runtime-ascend-cann9.0.0:2.1.2`（Phase B 用其快照 `vllm-phaseb-ascend-snapshot`）
**容器:** `vllm-phaseb-ascend-cann9.0.0`　**Python:** 3.11.15　**torch/torch_npu:** 2.10.0+cpu / 2.10.0　**triton:** 3.5.1
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，全链路 serve + 推理
**模型:** Qwen3-4B（`/data/models/Qwen/Qwen3-4B`，modelscope 下载 7.6G）
**NPU 绑定:** **NPU 1**（NPU 0 有他人 `pytest` 进程占用，故换绑；仅 Python 安装阶段无关设备）

ascend 是此前 flag_gems `j0`/`log2` 缺失致 import 崩溃的两个后端之一，故本次 E2E
同时是**修复后 5.3.4 wheel 的在硬件确认**。全链路 serve + 推理一次跑通，910B4 上
Qwen3-4B 贪婪解码输出连贯英语。这也是首个 **aarch64 + Python 3.11** 组合的 repack。

### Repack —— 复用 Phase A 产物（aarch64 / cp311）

Phase A（2026-08-10 于 hw25 build-image 内）产出 4 个 `+flagos` wheel，零泄漏扫描通过，
平台 tag 正确，用户已上架 `flagos-pypi-ascend`：

```
vllm:                   0.20.2+flagos     ✅  empty，py3-none-any
xgrammar:               0.2.4+flagos      ✅  cp311-cp311-manylinux_2_26_aarch64（py3.11+aarch64）
compressed-tensors:     0.15.0.1+flagos   ✅  纯 py3
opencv-python-headless: 5.0.0.93+flagos   ✅  cp37-abi3-manylinux_2_28_aarch64（稳定 ABI）
```

### 安装 —— ✅ 单步 + 插件干净安装

`vllm==0.20.2+flagos` 从 `flagos-pypi-ascend` 单步安装，torch/torch_npu 从镜像保留，
无公有 torch/cuda/triton 链。`vllm-plugin-FL` 走 `pip install --no-build-isolation -e .`
（`VLLM_VENDOR` 未设 → 纯 `py3-none-any`，`vllm-plugin-fl 0.0.0+gf4ebc258f`）。

### serve + 推理 —— ✅ 成功（3 处修复）

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 1 | import 崩溃 `libdevice has no attribute 'j0'` | 镜像烘焙的是 **旧** 5.3.4 wheel（重推前），FlagTree `triton.language.extra.cann.libdevice` 缺 `j0`/`log2`，`_patch_missing_symbols` 无 fallback 可打 | 从 `flagos-pypi-ascend` **强制重装 5.3.4**（重推后 wheel）→ `j0=True log2=True`。**即用户重推 5.3.4 的硬件确认** |
| 2 | serve 启动崩溃 `coreDim is invalid (value 0)`（EngineCore init） | 模型构造 `register_buffer("_k_scale", torch.tensor(1.0))` 经 `aten::lift_fresh` 被 flag_gems 拦截，标量 tensor 算出零 grid，NPU KernelLaunch coreDim=0 | `dispatch/config/ascend.yaml` `flagos_blacklist` 加 `lift_fresh` / `lift_fresh_copy` / `_to_copy`（纯拷贝，回退 torch_npu 无损） |
| 3 | 推理崩溃 `OSError: Could not load this library: .../libatb.so`（`_npu_reshape_and_cache` / `_npu_rotary_embedding`） | 基础镜像 `vendor.sh` 仅设 CANN toolkit `LD_LIBRARY_PATH`，**未 source NNAL/ATB `set_env.sh`** → `ATB_HOME_PATH` 空，ATB 后端算子（reshape_and_cache / rotary_embedding）加载失败 | serve 前 `source /usr/local/Ascend/nnal/atb/set_env.sh`（解析到 `cxx_abi_1`，libatb 就位）。**镜像侧缺口**——应烘焙进 base image env（见待办） |

修复后 serve 达 `Application startup complete`（KV cache 2048-token / 50.5x 并发，NPU 1）。
**首次推理**首 token 延迟高（首请求逐 shape 编译 triton/NPU 内核，60s curl 超时 →
加长即返回）；rms_norm/rotary/silu_and_mul 均正确 dispatch，全程 0 error。

### Stack 验证（ascend-cann9.0.0，✅ E2E 通过 2026-08-10）

```
torch/torch_npu: 2.10.0+cpu / 2.10.0  ✅  from 镜像
triton:       3.5.1                    ✅  （+ triton_ascend）
vllm:         0.20.2+flagos           ✅  empty，复用 Phase A aarch64 产物
vllm_fl:      0.0.0+gf4ebc258f        ✅  纯 Python（VLLM_VENDOR 未设）
flag_gems:    5.3.4（重推后，强制重装）✅  j0/log2 已修；3 op 黑名单（lift_fresh/lift_fresh_copy/_to_copy）
NPU device:   ✅ NPU 1                 910B4（NPU 0 被他人占用）
vllm import:  ✅
vllm serve:   ✅  application startup complete（Qwen3-4B TP=1, max-len 2048, mem-util 0.6, enforce-eager）
Inference:    ✅  "The capital of France is" → " Paris. The capital of Germany is Berlin.
                  The capital of Italy is Rome..." 连贯英语；32 token，finish_reason=length，
                  POST /v1/completions 200 OK，无 coreDim/libatb/dtype 错
```

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| `lift_fresh`/`lift_fresh_copy`/`_to_copy` 黑名单对齐 Mac 源码并提 PR | ✅ 已提 | **[PR #361](https://github.com/flagos-ai/vllm-plugin-FL/pull/361)**（flagos-ai/vllm-plugin-FL，分支 `ascend-blacklist-lift-fresh`→`release-0.2`）：`dispatch/config/ascend.yaml`；coreDim=0 标量崩溃规避，回退 torch_npu 无损。根治方向：flag_gems 标量/极小张量 grid 下限保护 |
| ATB `set_env.sh` 烘焙进 base image env | ✅ 已提 | **两后端分属不同 PR**：cann9.0.0 = **[PR #353](https://github.com/flagos-ai/build-infra/pull/353)**（`base/ascend-cann9.0.0` 在 CANN 之后 source NNAL/ATB `set_env.sh`）；cann8.5.0 = **[PR #354](https://github.com/flagos-ai/build-infra/pull/354)**（补 NNAL）+ **[PR #355](https://github.com/flagos-ai/build-infra/pull/355)**（捕获 NNAL/ATB env 进 `vendor.sh`）。`ATB_HOME_PATH` / ATB lib path 进 `vendor.sh`，消除运行时手动 source；否则 ATB 后端算子（reshape_and_cache/rotary_embedding）在裸 shell 崩溃 |
| flag_gems 5.3.4 重推 v2 镜像刷新 | 🔄 进行中 | 现镜像烘焙旧 wheel，须强制重装才可用；全部 17 个 v2 runtime 镜像重建后消除（run 31365995958，用户驱动） |
| ascend `+flagos` wheel 上架 | ✅ 已上传 | 4 个 wheel 已上架 `flagos-pypi-ascend`（用户上传） |

**相关提交：** plugin 黑名单已提 **[PR #361](https://github.com/flagos-ai/vllm-plugin-FL/pull/361)**（`ascend-blacklist-lift-fresh`→`release-0.2`，commit baeafde）。wheel 复用 Phase A + 用户上传（无落库）；ATB env 1 处在容器内，base image 待对齐。

### 后续（2026-08-24）：ascend 双后端 0.20.2 全路径 F/T 双编译器 E2E 全 ✅

两个 ascend 后端（cann9.0.0 @ hw25、cann8.5.0 @ hw26）**release-0.2 实测**（不预置黑名单、
不回移植 0.24.0 线）：serve + 推理（Qwen3-4B）F（flagtree）与 T（triton）双路径均 E2E 通过，
64 token 贪婪解码连贯。矩阵 0.20.2(T)/0.20.2(F) 两列由 ⬜ 翻 ✅。

| 后端 | 节点 | F（flagtree） | T（triton） |
|---|---|---|---|
| cann9.0.0 | hw25 | ✅ | ✅ |
| cann8.5.0 | hw26 | ✅ | ✅ |

相比 §2.8（2026-08-10 仅 F 路径）实测新增一处黑名单，与前 3 处（lift_fresh / lift_fresh_copy /
_to_copy）同落 `dispatch/config/ascend.yaml`（cann8.5.0 / cann9.0.0 共用）：

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 4 | 推理崩溃 `pow_scalar` | flag_gems `_ascend/ops/pow.py` 用三个 `tl.constexpr()` **OR 条件**做分支守卫（非 `a < b < c`）。**两后端根因不同**：cann8.5.0（flagtree 0.6.0+ascend3.2）F/T 双路径均拒绝；cann9.0.0（flagtree 0.6.1+ascend3.5）仅 vendor triton 拒绝，F 路径已修 | `flagos_blacklist` 加 `pow_scalar`（回退 torch_npu 无损；8.5.0 遮 F+T、9.0.0 仅需遮 T），已提 **[PR #402](https://github.com/flagos-ai/vllm-plugin-FL/pull/402)**（`ascend-blacklist-pow-scalar`→`release-0.2`） |

**两后端修补差异（`dispatch/config/ascend.yaml` 共用，但根因/作用域不同）：** pow_scalar 黑名单是
**共享条目**，但两后端触发的路径不同——差异源于 **flagtree 版本**：cann8.5.0 用 flagtree
0.6.0+ascend3.2，其仍拒绝 pow.py 的 `tl.constexpr()` OR 条件（F 路径也崩，故黑名单遮 F+T）；
cann9.0.0 用 flagtree 0.6.1+ascend3.5，已修此缺陷（F 路径通过，仅 vendor triton 仍拒绝，黑名单
只需遮 T）。反向的差异是 §2.8 修复 #1 的 j0/log2：那是 flagtree 0.6.1（cann9.0.0）libdevice 缺口，
cann8.5.0 的 flagtree 0.6.0 libdevice 无此问题，故 8.5.0 无需重装 5.3.4（实测其 j0 缺失但 import
不崩）。即：**8.5.0 多修 pow_scalar 的 F 路径、少修 j0/log2；9.0.0 反之。**

NPU 冷启动 JIT 极慢：hw25 T 路径首请求 872s（逐 shape 编译 triton/NPU 内核），稳态 0.1~0.2 tok/s，
64 token decode 约 11~15 min。慢≠挂：以 `generation_tokens_total` 增量 + `num_requests_running` 归零
判断完成，勿以客户端 curl 超时误判卡死。

**构建源与上游 PR 追踪（fork 分支 provenance）：** #361 与 #402 是**两个独立分支**，各自只含一半
黑名单（#361 = lift_fresh 系 3 条、#402 = pow_scalar 1 条），0.20.2 ascend 两后端需**四条全齐**。
上游 merge 由 plugin 团队掌控、无法控制，故 wheel 从 fork 上的合成分支构建（`vllm-plugin-wheel.yml`
`plugin_repo` 指 fork、`plugin_ref` 指合成分支 SHA），与其它后端从 fork 打 pre-merge wheel 同一流程。

| 合成分支 commit（构建源） | 上游原始 commit | 上游 PR |
|---|---|---|
| `00cc275` lift_fresh 系 | `baeafde` | [vllm-plugin-FL#361](https://github.com/flagos-ai/vllm-plugin-FL/pull/361) |
| `05f246b` pow_scalar | `13a91ef` | [vllm-plugin-FL#402](https://github.com/flagos-ai/vllm-plugin-FL/pull/402) |
| `2b6b635` pow_scalar 注释修正 | `e084195` | [vllm-plugin-FL#402](https://github.com/flagos-ai/vllm-plugin-FL/pull/402) |

合成分支 = `tengqm/vllm-plugin-FL:ascend-blacklist-release-0.2` @ `2b6b635cd93c5578ba945cf935f7c7f7e1d5d882`
（基于 `release-0.2` @ `825c1cd` cherry-pick 三笔，内容与上游逐字节一致，SHA 因 cherry-pick 重写
committer/date/parent 而不同）。wheel 版本串 `0.2.0+g2b6b635.d20260824` 把构建 SHA 烙进元数据，app 镜像
安装 pin 带进 image_tag，status_matrix 记 image_tag → 版本串 → 上游 PR，追踪链闭合。**#361/#402 merge 进
上游 release-0.2 后，用上游新 HEAD 重打 wheel（内容逐字节相同，仅版本串 SHA 换上游值），届时删除本表。**

**PR 追踪约定（6 个 app × 17 后端 × F/T 双路径，PR 数量会很多）：** 持久源 = status_matrix 的
`backends.<name>.prs:` 字段（结构化，已被 enflame/kunlunxin/sunrise 使用，记录「该后端 image 依赖的
上游 PR URL」），merge 后仍保留；临时源 = 本表这类 fork-SHA → PR 映射，仅在 PR 未 merge 期间存在、
merge + 重建后即删。**每后端跑通时：上游 PR 进 `prs:`（永久）、fork 合成分支映射进 report「后续」（临时）。**


---

## 2.9 sunrise-tangrt1.2.0（PTPU：✅ 官方 Triton E2E 通过；FlagTree 解码挂死缺陷 —— ✅ 已修复，见文末"后续"）

**有可用回退路径，并非硬阻塞。** 默认的 FlagTree 编译器下，serve 可起、预填充正常返回，
但进入**解码阶段即挂死**，卡算力占用钉在 100% 且永不退出。切到官方 Triton（`/opt/triton`）即可绕开。

**回退操作：** 在起 serve 的**同一个 shell** 里先执行 `compiler triton`（该命令只改当前 shell 的
`PYTHONPATH`，把 `/opt/triton` 前置），再启动 serve。`compiler flagtree` / `compiler` 切回或查看当前编译器。

官方 Triton 下 **serve + 推理端到端已验证通过，推理结果正确**。

**根因：FlagTree（triton 3.6.0）代码生成缺陷。** flag_gems `_sunrise` 后端的
`flash_varlen_fwd_kernel` 在**解码 + GQA** 特化（`seqlenq_ngroups_swapped`：
`max_seqlen_q==1`、q 头 32 > kv 头 8，导致 `cu_seqlens_q=None` 被 Triton 从签名中丢弃）
下被编译成不终止的 kernel。同一 kernel、同一入参改用官方 Triton 编译则正确完成——仅切换
编译器即完成归因。预填充特化（真实 `cu_seqlens_q`、batch stride 全 0）编译正常，故只有解码卡死。

已产出**不依赖 Docker / vLLM / 模型**的最小复现（`replay_min.py` + 277 KB 捕获入参），
FlagTree 下挂死、官方 Triton 下通过，待交厂商。

**影响：** 一旦挂死，该卡持续占用至设备/驱动复位或整机重启；`pt_smi -i <n> -r` 无法清除。

**后续（2026-08-19）：缺陷已修复。** 根因锁定在旧 vendor 标签
0.6.0+sunrise3.6（FlagTree **PR 978 之前**）的 sunrise 后端代码生成；
PR 978 重写 sunrise backend pass pipeline 并删除 `add_split_dot`（疑似
修复点）。已把 sunrise wheel 构建固化到 `packaging/flagtree/sunrise`
（PR #447→#450，22.04 + clang-14/lld-14 交付链，六道 CI gate 全过），
从 FlagTree main（含 PR 978）重建 wheel 后 A/B 实证：**解码 0.4 tok/s
（非终止）→ 2.4~2.5 tok/s（终止，输出连贯）**。节点复验在无
`LD_LIBRARY_PATH` workaround、无手动 tang 软链下通过（RUNPATH
`$ORIGIN`、md5 门禁、import/serve/推理全绿，详见
`report-vllm-0.24.0.md` §11.5）。wheel 沿用原版标签上传
`flagos-pypi-sunrise`，可 drop-in 替换；本单元格 F 路径由"挂死"升级为 ✅。

**复测（2026-08-20）：0.20.2(F) 路径在 rebuilt wheel 下全绿。** 直接在
0.20.2 环境复测 FlagTree 路径（`compiler flagtree`，runtime 2.1.2 已烘焙
rebuilt wheel，`/opt/flagtree/triton/_C/libtriton.so` md5 924b1c0d 匹配
§11.5 门禁值），serve `/data/nmodels/Qwen3-8B` 达 `Application startup
complete`；推理连贯（knowledge "Paris..." / math "56"）、decode 正常终止
（2 请求均 `finish_reason=length`，无挂死）、崩溃标记 0。A/B 结论在
0.20.2 自身版本下成立，矩阵 `0.20.2(F)` 格 ❌→✅。

### 环境

| 组件 | 版本 |
|---|---|
| Python | 3.10.20 |
| torch | 2.11.0+cpu |
| torch_ptpu | 0.2.3+torch2.11 |
| FlagTree（triton） | 3.6.0 |
| flag_gems | 5.3.4 |
| vLLM | 0.20.2+flagos |
| 设备 / 驱动 | PTPU，sunrise / tangrt 1.2.0，tang 0.24.0 |

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| 回退：切官方 Triton 运行 | ✅ E2E 已验证 | `compiler triton` 后 serve + 推理端到端通过、结果正确;当前 sunrise 的可交付路径 |
| FlagTree flash-attn 解码 kernel 挂死复现交厂商 | ✅ 已交付 | 最小复现（Docker-free，A/B 编译器归因）已交 FlagTree 团队 |
| FlagTree 侧修复落地 | ✅ 2026-08-19 | PR 978 已合入；重建 wheel 后 A/B 实证解码 0.4→2.4 tok/s；F 路径升级 ✅（上文"后续"，详见 0.24.0 §11.5） |


## 2.10 kunlunxin-xre5.37.1（P800 XPU：✅ 双编译器 E2E 通过；解码乱码 / 假死 —— ✅ 双闭环）

**结论（2026-08-22~23）：** 0.20.2 双编译器路径均 E2E 通过 —— FlagTree（默认）
7/7（7.3~9.8 tok/s）、Triton 3.6.0 3/3（5.7~7.3 tok/s），serve + 推理连贯。
此前两个阻塞（解码乱码、解码假死）均已 A/B 定位根因并闭环；旧阻塞（三处
attention 内核编译失败）由厂商插件层 **PR #268**（xtorch_ops 原生 attention
backend，不碰 Triton 编译）+ triton 3.6.0 升级（#469）解除。解码乱码根因详见
[`kunlunxin-decode-repetition-scale-bug.md`](kunlunxin-decode-repetition-scale-bug.md)。

### 阻塞点与闭环

**P2 解码乱码 —— 插件 patch 传错 attention scale（已闭环，PR #400）。**
`patch_decode_attention`（`patch.py:401`）把 decode 借道
`xtorch_ops.prefill_attention` 时传 `alpha=scale`（≈0.0884），而
`prefill_attention` 期望 adjusted scale（`scale×√head_size` = 1.0，原生 prefill
路径即如此）。α 小 √128 ≈ 11.3 倍 → QKᵀ 打分整体收缩 → softmax 趋平 → 输出
重复退化（greedy 下高频 token 主导）。一行修复 `alpha = scale × √head_size`
后，probe 对照 native 路径 max error 0.0014、serve 输出连贯。修复已上提
vllm-plugin-FL **PR #400**（base **release-0.2** = 0.20.2 发布线；upstream main
已删除 vendor/kunlunxin 目录，0.24.0 线无挂点），body 含双编译器验证记录。

**P1 解码假死 —— 触发源 = `XPU_EVENT_KL3_ENABLE=1`（已闭环，配方去掉该行）。**
KL3 事件/同步路径（`torch_xmlir/xre/so/libxpucuda.so.515.58.kunlun`，与
get_cluster_clock 同 .so）在异步提交路径引发设备异常。A/B 单变量法：基线
（KL3=ON）6 次启动 2 次跑通、9 次 XPUW err-task（get_cluster_clock + Xid
KL_XID_KERNEL_EXCEPTION，内核态 dmesg，签名跨事件一致）；**unset KL3 后
flagtree 7/7 + triton 3/6.0 3/3 全跑通 + dmesg 零新事件**。CUDA_LAUNCH_BLOCKING=1
亦可消除（错误提示自带）但吞吐减半。假死链路：解码步设备异常 → 看门狗 20min 后
报 get_cluster_clock → error 702 在 patch.py:72 compute_slot_mapping 浮出 →
退出期 `_prepare_to_exit→synchronize` 永久挂起。与具体算子无关（无需换
flag_gems 实现）。

**app 镜像 serve 慢 —— 根因 = env 缺失（export 缺陷），不是 block-size（2026-08-23
闭环，PR #478）。** 原 configs.yaml kunlunxin 仅 `env.base`、无 `env.app.vllm` → app
镜像零 serve env；补四变量（`VLLM_FL_PLATFORM=kunlunxin`、`VLLM_FL_PREFER=flagos`、
`USE_FLAGGEMS=1`、`VLLM_FL_FLAGOS_WHITELIST=silu_and_mul,rms_norm,rotary_embedding`，
#476）后，plain `docker run <app镜像>` 仍慢到 ~0.1 tok/s。2×2 控制实验定案：同一镜像、
同一 CLI、同一 block-size=16，仅差这四变量 → 6.4 vs 0.1 tok/s，env 是差别因子，bs 不是。
链路断点在 Containerfile：`/etc/profile.d/app_env.sh` 以裸 `KEY=value` 写入，vllm-serve
source 后 `exec` 新进程 → 非 export 的赋值随 sourcing shell 消失，到不了 exec 的 server。
修复（PR #478）：runtime/Containerfile + app/vllm/Containerfile + app/megatron 两个
Containerfile 写 profile.d 时统一 `sed 's/^/export /'` 前缀；同时修正 app/vllm 默认 CMD
模型路径 `/data/models/Qwen/Qwen3-4B` → `/data/models/Qwen3-4B`（旧路径在参考节点不存在，
plain `docker run` 直接 model-not-found）。`configs.yaml` 数据与 `generate_matrix.py`
序列化（保持 `KEY=value`）不动 —— export 属于 Containerfile 层，直接 CLI 构建也覆盖。
重建后 plain `docker run <image>`（无参数，走默认 CMD）验证：`/data/models/Qwen3-4B`
正常加载，exec 后的 server 进程 `/proc/1/environ` 含全部四变量（export 生效的直接证据），
推理 4.3~9.4 tok/s 且输出连贯（对照修复前 0.1 tok/s 乱码）。app 镜像指纹：
`vllm0.20.2-kunlunxin-xre5.37.1:2.1.2-0.2.1_g8236c0a.d20260821`（ID 229fda5f9ee9…）。
**KL3 刻意不固化**（修复 = 缺省，容器默认 env 本就干净）。

### 环境

| 组件 | 版本 |
|---|---|
| 镜像 | flagos-runtime-kunlunxin-xre5.37.1:2.1.2-vllm-kx-20260822（ID 56c73455d509） |
| Python | 3.10 |
| torch | 2.9.0+cu129 |
| FlagTree（triton） | 0.6.1+xpu3.6 |
| Triton | 3.6.0+gitcd2d6c1b |
| flag_gems | 5.3.4 |
| xtorch_ops | 0.1.2935+50a5d6a4 |
| vLLM | 0.20.2+flagos |
| 设备 / 驱动 | P800 XPU / 5.37.1 |

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| alpha 修复上提 vllm-plugin-FL | ✅ PR #400 | base release-0.2（0.20.2 发布线）；body 已补双编译器验证记录 |
| app 镜像 serve E2E（plain docker run） | ✅ PR #478 | 2026-08-23 重建后验证：默认 CMD 模型路径 + export env + 4.3~9.4 tok/s |
| Qwen3.6-27B 回归 | ⬜ | patch 初衷是规避 layer 43+ decode NaN，修复 scale 后须重验 |
| 源文档配方更正（去掉 KL3 行） | ⬜ 待拍板 | 复刻源文档 3 处含 `XPU_EVENT_KL3_ENABLE=1`，已定负面教材不改 |
| 0.24.0 验证 | ⬜ | upstream main 已删 vendor/kunlunxin 目录，0.24.0 线无插件挂点 |


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
| app 镜像 Containerfile | `FROM runtime` + pip install vllm + plugin-FL | ✅ app/vllm/Containerfile + app/megatron×2；vllm 线已验证 |
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

### 5.3 NVIDIA 统一 empty 模式（2026-08-23 决策，已定案）

**决策：** NVIDIA 并入 empty 模式，全线统一。standard 构建（官方预编译
wheel）退役，`build-and-repack.sh` 移除 nvidia 分支，"都走统一个模式"。

**背景：** NVIDIA 原本用 standard 构建（含 vllm 自带 CUDA kernel），其余
后端用 empty + plugin-FL/flag_gems 算子。§5.2 的"一份通用 `+flagos` empty
wheel"模型此前只覆盖非 NVIDIA 后端。

**决策理由：**
- **统一与可移植优先。** empty wheel 是 `py3-none-any`，纯 Python，一份
  产物跨后端（含 CPython 版本，0.20.2）复用；standard wheel 与
  ABI/平台绑定，无法进入统一管线。
- **单步安装的前提是同一 wheel。** app 镜像单步安装 `vllm==X+flagos`，
  若 NVIDIA 保留 standard，则同一 vllm 版本需维护两套 wheel，版本 bump
  时校验面翻倍。
- **性能基准不再是门控。** 0.24.0 已先行实证（2026-08-16）：nvidia 空模式
  双编译器（flagtree 3.6.0 / triton 3.6.0）Qwen3-4B E2E 通过，见
  `report-vllm-0.24.0.md`；empty 模式下硬件算子由 flag_gems（Triton）提供，
  0.24.0 线上的 NVIDIA 性能结论为全线统一提供了同源证据。0.20.2 的
  NVIDIA empty 验证接续进行（见 §2.1）。

**权衡确认：** standard 用 vllm 调优过的 CUDA kernel，通常最快；empty 放弃
这些，换取全线统一与单一可移植 wheel。基准门控撤销后，统一成为明确目标。

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
