# vllm 0.20.2 repack — 标准流程（Playbook）

> 本文对应原报告第 1 部分（§1.1–1.8）与第 6 部分（弯路记录）。
> 自动化边界、风险与痛点、ADR 见 [`decisions.md`](decisions.md)。

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

- **empty** —— 适用所有后端（NVIDIA 于 2026-08-23 并入）：
  `VLLM_TARGET_DEVICE=empty` 从源码编译不含硬件 kernel 的 vllm；硬件算子由
  vllm-plugin-FL + flag_gems 提供。产物为 `py3-none-any`，纯 Python。
- ~~**standard**~~ —— ~~仅 NVIDIA~~：~~`pip download` 官方预编译 wheel，含 vllm
  自带 CUDA kernel（`_C`）~~。**已退役（2026-08-23，见 [§5.3](decisions.md)）**

> 2026-08-23 起全线统一 empty 模式（"都走统一个模式"），standard 构建退役，
> 决策记录见 [§5.3](decisions.md)。

## 1.3 Repack

使用 `packaging/vllm/repack.py`（分类规则见 `packaging/vllm/config.yaml`）处理 wheel：

1. **加 `+flagos` 版本后缀** —— 主包与所有递归发现的间接依赖统一处理。
   保持原始 platform tag，不改 WHEEL Tag。
1. **Metadata-Version 从 2.4 降级为 2.2** —— 方便 Nexus 解析。
1. **METADATA 正则替换不留空行** —— 对 `License-File`、`Dynamic:` 行的删除
   必须吃掉尾随换行（正则加 `\n?`）；否则 header 在空行处被截断，后面所有
   `Requires-Dist` 对 pip 不可见（曾导致 `ModuleNotFoundError`，见
   [§2.1](backends/nvidia.md)）。
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
   共享索引要么维护 3×2 矩阵、要么拆成多索引安装——反而更脆，故放弃
   （[§5.2](decisions.md)）。

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
> PEP 440，但跨后端尚未全部实测（[§5.1](decisions.md)）。显式带 `+flagos`
> 则无歧义，直接锁定 repacked wheel。

> **为什么单步就够（曾经需要两步）？** repack 若只剥掉 vllm 自身的 torch
> 声明、却漏掉间接依赖（如 xgrammar、compressed-tensors）的 torch 声明，
> pip 仍会从 Aliyun 拉一个更高的 base 版本 torch → 覆盖 vendor 的本地版本
> torch。早期 MetaX 因此被迫用 `--no-deps` 两步锚定（见
> [§2.2](backends/metax.md)）。
> **PR #280** 让 repack **递归**把所有间接依赖 pin 到 `+flagos` 后，torch
> 约束不再泄漏，单步安装即安全——已在 mthreads 上实测（131 包依赖树零
> torch/triton/nvidia 泄漏，见 [§2.3](backends/mthreads.md)）。

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
  编译 C 扩展已退役，2026-08-23，见 [§5.3](decisions.md)）：
  `pip install --no-build-isolation .`。硬件算子由 plugin 的 dispatch 机制
  路由到 flag_gems（Triton）。构建产物为 `py3-none-any` wheel，一份跨后端
  复用。
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
  编于 numpy 1.x ABI，不能跑 numpy 2.x（[§2.4](backends/hygon.md)）。当前
  pin 的 `2.2.6` 是坏的。

**真正决定 per-backend numpy 版本的两个约束：**
1. **Python 版本上限** —— py3.10 不支持 `numpy>2.2.6`。
2. **厂商 torch 的 numpy ABI** —— torch 编于哪个 numpy ABI 决定其运行时下限/
   上限（编于 1.x 的 torch 要 `<2`；编于 2.x 的向后兼容 1.x）。

`opencv-python-headless` 声明的 `numpy>=2` **不是真实约束**——它是针对 numpy
2.x 编译、运行时向后兼容 1.x 的 wheel，实测在 numpy 1.26.4 上功能完好
（[§2.4](backends/hygon.md)）。历史上的 numpy bump/revert 有一半是被这个
faked 声明误导的（见 §6）。

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

**待建（⬜，记录写就时的状态）：**

| 文件 | 用途 |
|------|------|
| `app/vllm/Containerfile` | `FROM runtime` → pip install vllm + vllm-plugin-FL |
| `.github/workflows/vllm-app.yml` | 完整 CI：repack → upload → build → verify → push |

---

## 6. 演进与经验（弯路记录）

标准流程（§1）不是一开始就有的，是三个后端踩坑收敛出来的。这里记录主要
弯路，供回看"为什么规则是现在这样"：

- **numpy 版本 saga（[§2.1](backends/nvidia.md)）** —— 曾三次改法：
  (a) FlagGems 设 pip 推荐的 `numpy==2.3.5` 并打 tag `v5.3.2` → Python 3.10
  后端不支持 `numpy>2.2.6`；(b) 把 numpy 下沉到各后端；(c) FlagGems 干脆不
  pin numpy。最终稳定在 §1.7：**FlagGems 不 pin，build-infra 按后端锁定**
  （3.12→2.3.5, 3.10→2.2.6）。
  **补记（[§2.4](backends/hygon.md) 修正的前提）：** 最初全局锁的就是
  `numpy==1.26.4`，触发 bump→revert→unpin 的关键推手之一是
  `opencv-python-headless 5.0.0.93` 声明 `numpy>=2`。但该声明是 **faked**——
  opencv wheel 编于 numpy 2.x、运行时向后兼容 1.x，实测 1.26.4 下 C-API 往返
  完好（[§2.4](backends/hygon.md)）。也就是说 opencv 从不构成真实的 numpy
  下限；真正的约束只有"py 版本上限"和"厂商 torch 的 numpy ABI"两条。教训：
  **升级前先分清依赖声明是真实 ABI 约束还是打包策略**——一个 `import` +
  C-API 往返测试即可证伪。
- **FlagGems tag 复用** —— 过程中出现过删除 `v5.3.2` 再用同名重打。破坏
  可复现性，**不应再做**——bug 修复用递增新 tag（§1.6）。
- **伪造 platform tag（[§2.2](backends/metax.md)）** —— MetaX 曾把
  `py3-none-any` 改写成 `cp38-abi3-manylinux...` 来抢过 Aliyun 原版。
  [§5.1](decisions.md) 否定：`+flagos` 版本号排序已足够，伪造 ABI 有害。
- **两步 `--no-deps` 安装（[§2.2](backends/metax.md)）** —— MetaX 曾因间接
  依赖 torch 泄漏被迫两步锚定。PR #280 递归 pin `+flagos` 后，单步安装即安全
  （§1.4），mthreads 实证。
- **`also_repack` 手工列表 → 递归发现** —— 早期手工维护"还需 repack 的
  间接依赖"列表；现由 `repack_recursive()` 在 repack 时解析实际依赖树自动
  发现，手工列表已废弃（§1.3）。
- **`--extra-index-url` 优先的误解（[§2.1](backends/nvidia.md)）** —— 早期
  以为 extra-index 会被 pip 优先；实际 pip 拉平所有索引按版本号选。让我们的
  wheel 胜出的始终是 `+flagos` 版本号，与索引主次无关。
- **厂商 torch 的 numpy ABI（[§2.4](backends/hygon.md)）** —— iluvatar、
  hygon 的厂商 torch 编译于 numpy 1.x，装到 numpy 2.x 的镜像里
  `tensor.numpy()` 直接 `Numpy is not available`。这不是 repack/vllm 的问题，
  是镜像里 torch 与 numpy pin 不配套；教训是**厂商 torch 的 numpy ABI 必须
  与 configs.yaml 的 per-backend numpy pin 对齐**，镜像构建时应烟测
  `tensor.numpy()`。
