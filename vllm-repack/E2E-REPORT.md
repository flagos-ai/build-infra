# vllm-repack — 端到端验证报告

## 0. 背景

vLLM 原生 wheel 包中包含对 Torch、Triton 等关键软件包的声明式依赖。
如果不作处理，在安装 vllm 到 FlagOS runtime 环境中时，
会覆盖现有环境中精心匹配、反复验证过的版本矩阵。
例如安装 vllm 时会带入非厂商支持的 Torch 版本或 Triton 版本。
vLLM 所依赖的其他包中，也可能存在这种情况（实际验证过程中证实这种情况确实存在）。

因此，需要对 vLLM 及其所声明依赖的所有软件包进行预处理，或称重新打包（repack），
去除其中关键依赖。避免在安装时破坏已经搭建好的环境。
重新打包后的 vLLM （及所牵涉的其他 Wheel）包要上传到位于 resource.flagos.net
的 Vendor PyPI 服务器上，供后续流程化验证使用。

本文档记录 vLLM 重新打包的方案及在各个后端上的调试、验证情况。

## 1. 总体原则与约束

### 1.1 设计决定

关键约束：

1. **PyPI 分离** — Vendor PyPI 只放 Repacked Wheel 包，其余依赖包从公网拉。
   不托管间接依赖的、无须处理的软件包，维护成本太高。
1. **尽量保留 deps 安装，不用 `--no-deps`** — repacked wheel 保留除黑名单外的所有 Requires-Dist。
1. 国内节点通常无法访问 pypi.org，所有额外依赖的下载走 Aliyun 镜像。

### 1.2 repack.py 实现要点

使用 `vllm-repack/repack.py` 脚本来实现重新打包。

1. 重新打包的 wheel 保持原始版本，暂不做额外版本号处理。
1. Wheel 的 Metadata-Version 要从 2.4 降级为 2.2 降级，方便 Nexus 解析。
1. 对 Metadata-Version 中 `License-File` 和 `Dynamic:` 行的正则替换后不能留下空行。

### 1.3 重打包流程

本活动的主要流程如下：

1. 选择待验证后端，确认 FlagOS Runtime 镜像为最新，即包含可用的 Torch、
   Triton/FlagTree、FlagGems 组合。

1. 到目标机上以 `-d` 方式启动测试用容器。

1. `docker exec` 进入测试用容器。

1. 从 resource.flagos.net/repository/flagos-filestore 下载指定版本的 vllm
   源码包，目前“指定版本”为 `0.20.2`。

1. 执行脚本，递归处理 vllm 源码包中的依赖，形成剥离依赖后的 wheel 包集合。

1. 将预处理之后 vllm 及其他 wheel 包上传到后端对应的 PyPI 服务器。

重新打包后的 `vllm` Wheel 包不包含“危险的”依赖信息，力争做到一键安装。

### 1.4 测试验证流程

1. 选择待验证后端，确认 FlagOS Runtime 镜像为最新，即包含可用的 Torch、
   Triton/FlagTree、FlagGems 组合。

1. 到目标机上以 `-d` 方式启动测试用容器。

1. `docker exec` 进入测试用容器。

1. 从 `resource.flagos.net/repository/flagos-pypi-<vendor>` PyPI
   源安装指定版本的 vllm 安装包，目前“指定版本”为 `0.20.2`。

1. 检查 vllm 安装成功。

1. 检查 Torch、Triton/FlagTree 等核心包版本未被破坏。

1. 克隆 `vllm-plugin-FL` 仓库并安装。

1. 检查 `vllm serve` 可以启动，处理各类启动问题。

1. 检查 `vllm serve` 执行推理操作成功。

在测试验证过程中，随时记录新的发现。

### 1.5 关于 vllm-plugin-FL 的处理

目前 vllm-plugin-FL 定位是上游 vllm 的插件，功能目标是适配不同模型、不同后端。
具体适配时可能需要做算子层面的选择，甚至是针对不同后端的定制。

vllm 使用 `VLLM_TARGET_DEVICE=empty` 时，可以保留其核心逻辑，方便适配，
是 vllm-plugin-FL 的既定技术路线。除 NVIDIA 的所有后端，都应采用 `empty` 模式。

方案测试验证阶段如果发现 vllm-plugin-FL 中的 Bug，需要向 GIT 仓库提交 Bug
和修复 PR。所有修复方案尽可能不打破 vllm-plugin-FL 项目的现有模型层适配机制、
算子层适配机制，以最小改动完成方案打通。

### 1.6 关于 FlagGems 的处理

验证过程中不使用 FlagGems 的 GIT 仓库 master head，一方面避免不必要的源码克隆，
另一方面保证验证过程使用确定的 FlagGems 版本。因此，需要从各个 Vendor PyPI
服务器下载最新版本的 FlagGems Python 安装包。
要使用的 FlagGems 版本与 FlagOS runtime 镜像中锁定的版本一致，
版本号记录于 configs.yaml 文件的全局属性 `flaggems`。

验证过程中可能发现 flaggems 中的 Bug，要先提 PR，合并之后，用新的 GIT Tag
重新打包，重新上传。具体流程使用 build-infra 的工作流 `flaggems-release.yml`。

### 1.7 工具链

**新建文件：**

| 文件 | 用途 |
|------|------|
| `scripts/repack_vllm.py` | 下载 vllm wheel → repack → twine upload 到所有 vendor PyPI |
| `app/vllm/Containerfile` | FROM runtime → pip install vllm + vllm-plugin-FL |
| `.github/workflows/vllm-app.yml` | 完整 CI：repack → upload → build → verify → push |

## 2. 后端验证记录

### 2.1 NVIDIA cuda12.8

**日期:** 2026-07-27/28  
**平台:** NVIDIA H20 (8×)  
**目标:** vllm 0.20.2 + vllm-plugin-FL, flagos-runtime-nvidia-cuda12.8:2.1.1

#### A. numpy 版本问题

vllm 依赖 `opencv-python-headless>=4.13.0` 声明 `numpy>=2; python_version >= "3.9"`。
FlagOS 的 runtime 镜像中锁定 `numpy==1.26.4` 不兼容。版本锁定来源为 FlagGems。
全部 14 个后端中没有任何 Vendor Torch 声明 `numpy<2`。

解决尝试：

1. 在 FlagGems 中设置 pip 所自动推荐的版本 `numpy==2.3.5`。FlagGems 打新 Tag `v5.3.2`。
   在若干后端造成版本不兼容问题。主要是问题是 Python 3.10 不支持 `numpy>2.2.6`。

1. 在 build-infra 中将 `numpy` 下沉到各个后端，允许各个后端各自定制 `numpy` 版本。

1. 在 FlagGems 项目中不设置 numpy 的版本，留给 pip 安装时自行决定。
   FlagGems 删除原来的 Tag `v5.3.2`，重新打 Tag `v5.3.2`，重新制作 Python Wheel 包。
   这意味着 build-infra 中“下放” `numpy` 版本的事情并没有在 FlagGems 层面彻底解决。
   现在的 FlagGems 在实际安装时使用 numpy 版本是不可预测的。

#### B. vllm 预处理

下载 vllm。注意这里下载的不是 `empty` 模式。
以后可能需要统一到 `empty` 模式。

```bash
pip download --no-deps --dest /tmp/vllm-dl "vllm==0.20.2" \
  --index-url https://mirrors.aliyun.com/pypi/simple
```

重新打包：

```bash
python3 vllm-repack/repack.py /tmp/vllm-dl/vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl
```

结果：有 7 个会导致 Torch、Triton 被覆盖的包进入黑名单。
这些包依赖被去除之后，保留的依赖包有 82 个。
vllm 之外的 6 个同样需要重新打包的第三方包记录到 `also_repack` 下，
在 vllm 中保留对它们的依赖。

上传重新打包后的 wheel 到 vendor PyPI：

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-nvidia/ \
  /tmp/vllm-repack/output/vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl
```

#### C. 安装检验流程

此次试验为使用容器，原因是为了方便调试。
在目标机创建虚拟环境后，安装运行时依赖（`torch`, `flagtree`, `flag_gems`, ...）。
版本锁定依据为 `configs.yaml` 中的 `nvidia-cuda12.8` 后端：

```bash
pip install \
  --index-url https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple \
  torch==2.10.0+cu128 torchaudio==2.10.0+cu128 torchvision==0.25.0+cu128 \
  flagtree==0.6.0 flag_gems==5.3.2 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.1 numpy==2.3.5
```

安装洁净版 vllm，注意不使用 `--no-deps`，不然 vllm 的其他依赖包都不会装。

TODO: 

- 这里的 `--index-url` 和 `--extra-index-url` 使用可能有问题。
- 0.20.2 这种版本锁定，pip 和 uv 都没有完美解决方案，尤其是跨仓库安装时。

```bash
pip install \
  --index-url https://mirrors.aliyun.com/pypi/simple \
  --extra-index-url https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  vllm==0.20.2
```

克隆并安装 `vllm-plugin-FL`：

```bash
git clone https://github.com/flagos-ai/vllm-plugin-FL
cd vllm-plugin-FL
VLLM_VENDOR=cuda pip install --no-build-isolation .
```

启动 vllm serve：

```bash
export VLLM_PLUGINS=fl
vllm serve /models/Qwen3.6-35B-A3B \
  --served-model-name "qwen" \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --trust-remote-code
```

启动测试推理：

```json
{"model":"qwen","choices":[{"message":{"content":"Here's a thinking process:\n\n1.  **Analyze User Input:**..."}}]}
{"usage":{"prompt_tokens":17,"total_tokens":145,"completion_tokens":128}}
```

✅ 推理成功。

---

#### D. 遇到的 Bug 及根因

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | `pip install repacked-vllm.whl` → vllm import 失败：`ModuleNotFoundError: No module named 'regex'` | METADATA header 在 `License-File` 删除留下的空行处截断。后面 82 行 Requires-Dist 对 pip 不可见 | 正则加 `\n?` 吃掉尾随换行 |
| 2 | `pip install` 升级 numpy 1.26.4 → 2.3.5，flaggems 崩溃 | `opencv-python-headless` 声明 `numpy>=2`，flaggems 声明 `numpy==1.26.4` | 放宽 FlagGems `pyproject.toml` 为 `numpy` 不锁定；configs.yaml 改为 `2.3.5` |
| 3 | vllm 安装后 `sqlalchemy` 完全消失 | flaggems 用了 `--no-deps`，其依赖未拉取。vllm 解析不需要 sqlalchemy → 被卸载 | 安装 flaggems 不用 `--no-deps` |
| 4 | `vllm serve` 警告 `_C.abi3.so: undefined symbol: _ZN3c1013MessageLoggerC1E...` | vllm 二进制 wheel 与主机 CUDA 的 ABI 不匹配——非致命，C 扩展优雅降级 | PoC 可接受。生产环境需用匹配 CUDA 版本编译 vllm |

---

#### E. 架构：各组件去向

```
pip install vllm==0.20.2
  │
  ├── --index-url: https://mirrors.aliyun.com/pypi/simple          ← 所有 safe deps
  └── --extra-index-url: https://resource.flagos.net/.../nvidia/simple  ← 仅 repacked vllm

解析过程：
  1. pip 向两边索引请求 vllm==0.20.2
  2. Aliyun: vllm-0.20.2.whl（原版，声明 torch 依赖）
  3. vendor PyPI: vllm-0.20.2.whl（repacked，torch 已删除）
  4. pip 选择 vendor PyPI（同版本，但 --extra-index-url 实际优先）
  5. pip 读取 repacked METADATA → 无 torch/triton/CUDA 依赖
  6. pip 从 Aliyun 解析其余 82 个 Requires-Dist
  7. 部分间接依赖（flashinfer、compressed-tensors）在自己的 METADATA 中声明 torch
  8. pip 发现 torch 已安装（2.10.0+cu128），约束已满足 → 跳过
```

#### F. 完整 Stack 验证（nvidia-cuda12.8）

```
torch:        2.10.0+cu128  ✅  (from vendor PyPI)
torchaudio:   2.10.0+cu128  ✅
torchvision:  0.25.0+cu128  ✅
flagtree:     0.6.0         ✅  (default compiler)
flag_gems:    5.3.2         ✅  (from vendor PyPI, numpy relaxed)
triton:       3.6.0         ✅  (side compiler at /opt/triton)
numpy:        2.3.5         ✅  (was 1.26.4)
pybind11:     3.0.3         ✅
ninja:        1.13.0        ✅
PyYAML:       6.0.1         ✅
vllm:         0.20.2        ✅  (repacked, from vendor PyPI)
vllm_fl:      loaded        ✅  (source build, VLLM_VENDOR=cuda)
CUDA:         True          ✅  (nvidia-smi works)
Inference:    Qwen3.6-35B-A3B ✅  (prompt_tokens=17, completion_tokens=128)
```

#### G. 后续步骤

1. **扩展到 nvidia-cuda13.3**（相同模式，不同 torch 版本）
1. **多厂商铺开** — metax（见 §2.2）、mthreads（见 §2.3）已完成；hygon、iluvatar、kunlunxin、cambricon 待排队

### 2.2 MetaX maca3.7.2.1

**日期:** 2026-07-28/31  
**平台:** MetaX C550 (8×, 64GB)  
**节点:** metax124 (bm-zksg-wx-zone1-d-mc550-64g-2-124)  
**MACA:** 3.7.2.0, Driver 3.8.30  
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL, flagos-runtime-metax-maca3.7.2.1:2.1.1

MetaX MACA 没有 NVIDIA CUDA 扩展，走 **empty 构建**（`VLLM_TARGET_DEVICE=empty`）
——编译不含硬件 kernel 的 vllm，硬件算子由 vllm-plugin-FL 的 metax vendor backend 提供。
除此之外，repack 规则、间接依赖处理、vllm-plugin-FL 安装均与 NVIDIA 相同。

> **状态（2026-07-31 更新）：端到端已完成。** ✅
> 在设备可见的 `vllm-serve-metax` 容器（metax124）里，用正确的 empty wheel +
> git 克隆的 vllm-plugin-FL，`vllm serve Qwen3-4B`（TP=1, `--enforce-eager`,
> `--gpu-memory-utilization 0.6`）成功启动并返回正确推理结果。

**真正的阻塞点：`reshape_and_cache_flash` 算子**

- empty wheel 不含`_C_cache_ops` C kernel。
  #319 的 substitution 从未生效（守卫恒真 + metax C550 > 禁用 Triton）。
  最终由 **#333** 修复：把该算子注册为 flaggems dispatch > op（`default.flagos`），
  metax 调用点改走 `CachedOp`。
- **#325（activation `F.silu`/`F.gelu`）在 empty wheel 上并不需要**——已实测验证。
  战略方向为使用 empty wheel，故 #325 已关闭。

#### A. 编译 empty vllm wheel

```bash
cd /workspace/vllm
VLLM_TARGET_DEVICE=empty MAX_JOBS=64   \
pip wheel --no-build-isolation --no-deps -w /tmp/empty .
# → vllm-0.20.2+empty-py3-none-any.whl (6.3 MB, 无 .so 文件)
```

#### B 重新打包

与 NVIDIA 流程相比，repack.py 有以下不同（均属临时试错方案）：

1. **去掉 METADATA 中 `Version:` 的 `+empty` 后缀** — PEP 440 本地版本
   不会被 `pip install vllm==0.20.2` 匹配
2. **重命名 `.dist-info` 目录** — `vllm-0.20.2+empty.dist-info`
   → `vllm-0.20.2.dist-info`
3. **改写 `WHEEL Tag:`** — `py3-none-any` →
   `cp38-abi3-manylinux_2_35_x86_64`，防止 pip 因平台匹配度
   优先选择 Aliyun 上的原版 wheel

```bash
python3 vllm-repack/repack.py /tmp/empty/vllm-0.20.2+empty-py3-none-any.whl
```

上传到 metax PyPI

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-metax/ \
  repacked-wheel.whl
```

递归间接依赖 repack

empty 构建（`VLLM_TARGET_DEVICE=empty`）跳过了这些硬件加速后端，
所以 empty vllm 实际上只有 **2 个**间接依赖声明了 torch/triton。

empty vllm 有 77 个间接依赖。其中 2 个在自己的 METADATA 中声明了
torch/triton：

| 包 | 声明的依赖 |
|---|---|
| `compressed-tensors`==0.15.0.1 | `torch>=1.7.0` |
| `xgrammar`==0.2.3 | `torch>=1.10.0` + `triton` |

逐一 repack（去掉 torch/triton 依赖，Metadata-Version 2.4→2.2 降级），
上传到 metax PyPI。其他间接依赖（`transformers`、`safetensors`、
`outlines_core`、`fastsafetensors` 等）仅在 extras 中声明 torch，pip
不会激活 extras，无需 repack。

**这不是 MetaX 专属问题**——所有 vendor torch 版本号低于 Aliyun
上游 torch 的后端都会遇到。

安装流程：

```bash
VENDOR=https://resource.flagos.net/repository/flagos-pypi-metax/simple
ALIYUN=https://mirrors.aliyun.com/pypi/simple

# 1. 运行时依赖（与 CUDA 一致：vendor 为主，Aliyun 补充）
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" \
  torch==2.8.0+metax3.7.2.0 torchaudio==2.4.1+metax3.7.2.0 \
  torchvision==0.15.1+metax3.7.2.0 flash_attn==2.6.3+metax3.7.2.0torch2.8 \
  flagtree==3.1.0+metax3.7.2.0 triton==3.0.0+metax3.7.2.0 flag_gems==5.3.2 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.3 numpy==2.3.5
```

vllm — 分两步（MetaX 专属：vendor torch 版本 < Aliyun torch）

```bash
pip install --no-deps --index-url "$VENDOR" vllm==0.20.2   # ① 锁定 repacked empty
pip install --index-url "$ALIYUN" vllm==0.20.2             # ② 补全 safe deps
```

> **为什么分两步？** `torch-2.8.0+metax3.7.2.0` 在 PEP 440 中排序低于
> `torch-2.11.0`（本地版本号排在基础版本号之下）。一步安装 `pip install
> --index-url $VENDOR --extra-index-url $ALIYUN vllm` 会触发 torch 降级。
> 先用 `--no-deps` 锚定 repacked vllm，再补全 safe deps，torch 不变。

TODO：优化这一步。

安装 vllm-plugin-FL — 纯 Python，不设 `VLLM_VENDOR`：

```bash
cd /workspace/vllm-plugin-FL
pip install --no-build-isolation -e .
```

#### 唯一真正的阻塞：`reshape_and_cache_flash`（由 #333 修复）

empty wheel 不含编译的 `_C_cache_ops` C kernel。MetaX flash attn 后端在
`fa_utils.py` 里把 `reshape_and_cache_flash` 直接绑定到
`vllm._custom_ops.reshape_and_cache_flash` → `torch.ops._C_cache_ops.*`，
首次前向时崩溃：

```none
AttributeError: '_OpNamespace' '_C_cache_ops' object has no attribute
'reshape_and_cache_flash'
```

**修复（#333）：** 把 `reshape_and_cache_flash` 注册为一等 dispatch op：

- `flaggems/flaggems.py` — 新增 `FlagGemsBackend.reshape_and_cache_flash`，转发到纯
  Triton 的 `flag_gems.fused.reshape_and_cache_flash`。
- `flaggems/register_ops.py` — 注册为 `default.flagos`（`_has_flaggems_op` 守卫）。
- `metax/impl/attention/utils/fa_utils.py` — 调用点改为
  `CachedOp("reshape_and_cache_flash")`，不再绑定 vllm 私有 C op。

留在 dispatch 抽象内（policy 驱动、可回退、厂商无关），不耦合 vllm 私有
`_C_cache_ops` ABI。[#333](https://github.com/flagos-ai/vllm-plugin-FL/pull/333)
取代了 [#319](https://github.com/flagos-ai/vllm-plugin-FL/pull/319)（已关闭）。

启动 vllm serve

在设备可见的 `vllm-serve-metax` 容器内（NCCL→MCCL 由 `pynccl_wrapper` patch
自动完成，无需额外 env）：

```bash
export VLLM_FL_DISPATCH_DEBUG=1        # 打印 dispatch 选择，便于确认 default.flagos
vllm serve /data/models/Qwen/Qwen3-4B --port 8031 \
  --gpu-memory-utilization 0.6 --enforce-eager \
  --trust-remote-code --max-model-len 2048
```

> **注意事项（实测）：**
> - MCCL communicator 冷启动很慢（~11 min，进程 15–25% CPU，看似 hang 实为在跑），
>   不要过早 kill。
> - 被 kill 的 engine-core 会以 `VLLM::EngineCore` 残留（`pkill -f "vllm serve"`
>   匹配不到）并占着显存，导致下次启动误报 "Free memory < desired"——需按 PID
>   或 `pkill -9 -f EngineCore` 清理。

#### 测试推理 —— ✅ 成功

serve 起来后：

```bash
curl -s http://127.0.0.1:8031/v1/completions -H 'Content-Type: application/json' \
  -d '{"model":"/data/models/Qwen/Qwen3-4B","prompt":"The capital of France is",
       "max_tokens":16,"temperature":0}'
```

返回：

```json
{"choices":[{"text":" Paris. The capital of Germany is Berlin. The capital of Italy is Rome.",
  "finish_reason":"length"}],
 "usage":{"prompt_tokens":5,"completion_tokens":16,"total_tokens":21}}
```

前向阶段日志确认算子走对了路：

```
Op 'silu_and_mul' using 'default.flagos' (kind=flagos, vendor=None)
Op 'reshape_and_cache_flash' using 'default.flagos' (kind=flagos, vendor=None)
```

全程无 `_C_cache_ops` / `_C.silu_and_mul` 报错。

#### 与 NVIDIA CUDA 后端的差异

| 步骤 | NVIDIA cuda12.8 | MetaX maca3.7.2.1 |
|---|---|---|
| vllm wheel | 标准版 — 从 Aliyun 下载 | **empty 构建**（`VLLM_TARGET_DEVICE=empty`） |
| repack 额外处理 | 无 | 去掉 `+empty` 版本后缀、修复 WHEEL Tag |
| vendor deps | torch/cu128, triton 3.6.0 | torch/metax, flash_attn/metax, triton 3.0.0 |
| vllm 安装 | 一步 `pip install` | 两步：先 `--no-deps` 锁定，再补 deps |
| vllm-plugin-FL | `VLLM_VENDOR=cuda` 编译 C 扩展 | 不设 VLLM_VENDOR；需 #333（reshape_and_cache_flash→flag_gems，见本节「唯一真正的阻塞」小节） |
| 间接依赖 repack | 相同的 6 个包 | 相同 |

#### Stack 验证 —— ✅ 完整端到端通过

在设备可见的 `vllm-serve-metax` 容器（metax124）内完成安装 + serve + 推理：

```
torch:        2.8.0+metax3.7.2.0    ✅  from vendor PyPI (未被降级)
torchaudio:   2.4.1+metax3.7.2.0    ✅
torchvision:  0.15.1+metax3.7.2.0   ✅
flash_attn:   2.6.3+metax3.7.2.0    ✅
flagtree:     3.1.0+metax3.7.2.0    ✅  默认编译器
triton:       3.0.0+metax3.7.2.0    ✅
flag_gems:    5.3.2                 ✅
vllm:         0.20.2                ✅  empty, repacked, vendor PyPI
vllm_fl:      installed             ✅  纯 Python 源码安装 + #333
MACA device:  ✅ 可见                mx-smi 正常 (C550 8×64GB)
vllm serve:   ✅ 启动成功            TP=1, enforce-eager, gpu-util 0.6
Inference:    ✅ 成功                Qwen3-4B, prompt=5 / completion=16 tokens
```

#### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| vllm-plugin-FL PR #333 | ✅ 已提，E2E 验证通过 | `reshape_and_cache_flash`→flag_gems dispatch（`CachedOp`）；empty wheel 唯一需要的改动 |
| vllm-plugin-FL PR #319 | ✅ 已关闭 | `_C_cache_ops` Triton fallback；守卫恒真从不生效，被 #333 取代 |
| vllm-plugin-FL PR #325 | ✅ 已关闭 | `_maca`→F.silu/F.gelu；empty wheel 上 dispatch 不走 vendor 路径，实测不需要（仅 +cpu wheel 有意义） |
| 更大模型 / graph 模式 | ⬜ | 仅测过 Qwen3-4B + eager；27B、35B-A3B、TP>1、graph 模式待测 |
| repack.py 改动 commit | ✅ | empty-wheel 支持 + 递归审计，见 PR #244 #247 |
| 间接 repack 自动化 | ✅ | `repack_recursive()` 自动发现 + repack |
| FlagGems pyproject.toml | ⬜ | build-system.requires 加 `wheel==0.45.0` |
| 其他 empty 模式后端 | 🔄 | mthreads ✅ 已完成（见 §2.3）；hygon 进行中；kunlunxin、iluvatar 待排队 |

### 2.3 mthreads-musa5.2.0

#### 流程 1：Repack & Upload（✅ 已完成 2026-08-01）

**执行命令：**
```bash
./scripts/repack-vllm-and-upload.sh --vendor mthreads --backend musa5.2.0
```

**上传的包：**
| 包名 | 版本 | 说明 |
|------|------|------|
| vllm | 0.20.2+flagos | 主包，empty build |
| xgrammar | 0.2.5+flagos | 间接依赖，strip torch/triton |
| compressed-tensors | 0.15.0.1+flagos | 间接依赖，strip torch |

**关键实现：**
- ✅ Empty build (`VLLM_TARGET_DEVICE=empty`)
- ✅ +flagos 版本后缀（主包 + 所有间接依赖）
- ✅ 递归依赖版本更新（A→B→C 链都更新为 +flagos）
- ✅ 上传到 `flagos-pypi-mthreads`

#### 流程 2：Install & Verify（✅ 已完成 2026-08-02）

**平台:** MTT S5000 (8×, 80GB)，节点 `mthreads`（JumpServer 别名）  
**MUSA:** 5.2.0-server，torch_musa 5.2.0  
**容器:** `vllm-verify-mthreads`，镜像
`flagos-runtime-mthreads-musa5.2.0:2.1.1`，以
`--runtime mthreads --env MTHREADS_VISIBLE_DEVICES=all -v /data:/data`
启动，`torch.musa.device_count() == 8`。

mthreads 与 MetaX 一样走 **empty 构建**（无 CUDA 扩展），repack 规则、间接
依赖处理、vllm-plugin-FL 安装均相同。唯一不同点：mthreads 的
`torch.device.type` 是 `"musa"`（其 flag_gems `device_name` 也是 `"musa"`，
是所有后端中唯一非 `"cuda"` 的 GPU 后端）——这直接引出下面「唯一真正的阻塞」小节。

**验证步骤：**
1. ✅ 启动 runtime 容器（带硬件访问，8× S5000 可见）
2. ✅ 验证 torch/triton/flaggems 环境
3. ✅ 安装 repacked vllm (+flagos)——`pip` 正确选中 `+flagos` 版本
4. ✅ 验证 torch 版本未被覆盖——`torch` 保持 `2.9.1+musa5.2.0`，triton 不存在
5. ✅ 安装 vllm-plugin-FL（纯 Python，不设 `VLLM_VENDOR`，同 MetaX）
6. ✅ 测试 vllm serve 启动（见下文 serve 小节）
7. ✅ 测试推理（见下文 serve 小节）

**安装验证结果：** 从 `flagos-pypi-mthreads` 安装
`vllm==0.20.2+flagos`（不使用 `--no-deps`），131 个包的依赖树中
**零** torch/triton/nvidia 泄漏：

- `torch` 保持 `2.9.1+musa5.2.0`（未被降级），`triton` 不存在
- `flag_gems` 5.3.2 / `flagtree` 0.6.0+mthreads3.6 / `numpy` 2.2.6 全部完好
- `xgrammar`、`compressed-tensors` 解析到各自的 `+flagos` 变体
- `vllm-plugin-FL` 安装成功，版本 `0.0.0+gd1327ae0a`，`fl` 插件正常激活

> **transformers 不是泄漏源** —— 其 torch 引用全部藏在未激活的 extras
> (`[torch]`/`[all]`/`[dev]`…) 之后，没有任何包激活它们。早前“transformers
> 拉入 torch”的判断实为未 pin 的 xgrammar bug（已在 PR #280 修复）。

#### 唯一真正的阻塞：flag_gems mul 设备门控回归（由 PR #5130 修复）

`vllm serve` 在模型加载阶段崩溃，命中 rope 的 `1.0 / freqs` 路径：

```none
rope: inv_freq = 1.0 / (base**...)  → Tensor.__rdiv__: reciprocal() * 1.0
 → flag_gems/ops/mul.py  mul_broadcast_func
 → torch.ops.aten.mul.Tensor.redispatch(_FALLBACK_KEYSET, a, 1.0)
RuntimeError: aten::mul.Tensor expected Tensor for 'other', found float 1.0
```

**根因——两步上游回归，并非 kernel bug。** Triton mul kernel 在 MUSA 上
所有路径均正确（实测 scalar/tensor/broadcast/fp16/bf16/int/out=/mul_/complex
误差全为 0）。崩溃纯粹来自设备门控：

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | 所有 mul 在 MUSA 上走 fallback，不走优化 Triton 路径 | FlagGems [#4666](https://github.com/flagos-ai/FlagGems/pull/4666)（"Move optimized mul to general path; use across MetaX and Hopper"）用 `device.type != "cuda"` 门控。MetaX 的 torch fork 报 `"cuda"` 故通过；mthreads 报 `"musa"`（唯一非 "cuda" 的 GPU 后端）被挤出 | PR [#5130](https://github.com/flagos-ai/FlagGems/pull/5130)：门控改判 `runtime.device.name` |
| 2 | fallback 对标量崩溃 | FlagGems [#4999](https://github.com/flagos-ai/FlagGems/pull/4999) 把 fallback 从 `torch.mul(a,b)`（可处理标量）改成 `aten.mul.Tensor.redispatch(...)`，而 `mul.Tensor` 要求 `other` 是 Tensor，python 标量 `1.0` 无法转换 | 同上——门控放开后 MUSA 直接走 Triton，不再进入损坏的 fallback |

**修复（PR #5130）：** 把门控从硬编码字面量 `"cuda"` 改为按激活后端的
设备名判断，符合库自身惯例（如 `_upsample_bilinear2d_aa.py` 用
`input.device.type == device.name`）：

```python
from flag_gems.runtime import device as runtime_device
_DEVICE_NAME = runtime_device.name        # "cuda" / "musa" / ...
...
if device.type != _DEVICE_NAME:           # was: != "cuda"
```

`device_name` 为 `"cuda"` 的后端（nvidia、metax、iluvatar、hygon…）不受影响；
mthreads（`"musa"`）自此走与其他后端相同的优化 Triton 路径。

> **对照 MetaX：** MetaX 之所以没有命中此坑，正因为它的 torch fork 报
> `device.type == "cuda"`，恰好通过门控；mthreads 是唯一暴露该回归的 GPU 后端。

#### 启动 vllm serve + 推理（✅ 成功）

选用 **DeepSeek-R1-0528-Qwen3-8B-FlagOS**（`rope_scaling.rope_type == yarn`）——
正是最直接触发上文「唯一真正的阻塞」小节所述崩溃的路径，用来验证修复最有说服力：

```bash
export MTHREADS_VISIBLE_DEVICES=all
vllm serve /data/DeepSeek-R1-0528-Qwen3-8B-FlagOS --port 8031 \
  --trust-remote-code --max-model-len 4096 --enforce-eager \
  --gpu-memory-utilization 0.85 --tensor-parallel-size 1
# NCCL→MCCL 由 pynccl_wrapper patch 自动完成，无需额外 env
```

serve 到达 `Application startup complete`（device_config=musa，MCCL 后端），
APIServer + EngineCore 进程均存活，全程无 `expected Tensor for 'other'` 报错。

测试推理：

```bash
curl -s http://127.0.0.1:8031/v1/completions -H 'Content-Type: application/json' \
  -d '{"model":"/data/DeepSeek-R1-0528-Qwen3-8B-FlagOS",
       "prompt":"The capital of France is","max_tokens":24,"temperature":0}'
```

返回：

```json
{"choices":[{"text":" a city in the north of France. It is famous for the Eiffel Tower, the Arc de Triomphe",
  "finish_reason":"length"}],
 "usage":{"prompt_tokens":6,"completion_tokens":24,"total_tokens":30}}
```

✅ 推理成功。修复单独一处即打通整条 serve 路径，本模型无需其他 flag_gems /
plugin 改动。

#### Stack 验证 —— ✅ 完整端到端通过

```
torch:        2.9.1+musa5.2.0     ✅  from vendor PyPI（未被降级）
triton:       (absent)            ✅  MUSA 无 triton，由 flagtree 提供
flagtree:     0.6.0+mthreads3.6   ✅
flag_gems:    5.3.2 + PR #5130    ✅  mul 门控修复
numpy:        2.2.6               ✅
vllm:         0.20.2+flagos       ✅  empty, repacked, vendor PyPI
vllm_fl:      0.0.0+gd1327ae0a    ✅  纯 Python 源码安装（无 VLLM_VENDOR）
MUSA device:  ✅ 8× 可见           mthreads-gmi 正常 (MTT S5000 8×80GB)
vllm serve:   ✅ 启动成功          TP=1, enforce-eager, gpu-util 0.85, port 8031
Inference:    ✅ 成功              DeepSeek-R1-0528-Qwen3-8B (yarn), 6→24 tokens
```

#### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| FlagGems mul 门控修复 PR #5130 | ✅ 已提，E2E 验证通过 | 门控改判 `runtime.device.name`；merge 后随 flag_gems release 打包进新 runtime 镜像 |
| repack & upload (+flagos) | ✅ 已完成 | vllm / xgrammar / compressed-tensors，见「流程 1」小节 |
| 更大模型 / TP>1 / graph 模式 | ⬜ | 仅测过 DeepSeek-8B + eager + TP=1 |
| 非 yarn 模型覆盖 | ⬜ | 可选，验证更广的 rope 路径 |

**相关提交：** `main` 分支 478de6b（repack）；FlagGems
[#5130](https://github.com/flagos-ai/FlagGems/pull/5130)（mul 门控）

## 3. 流程总结

### 3.1 可自动化部分

| 任务 | 方式 | 状态 |
|------|------|------|
| 下载 vllm wheel | `pip download`（简单，每次相同） | ✅ |
| 运行 repack.py | 脚本确定性强，输入式：wheel + config.yaml | ✅ |
| 上传到 vendor PyPI | `twente upload` + token（CI 步骤） | ✅ |
| 验证 METADATA（无空行、deps 正确） | 检查：`wc -l`、`grep Requires-Dist`、removed vs retained 计数 | ⚒️ 需要脚本 |
| 构建/上传到全部 vendor PyPI | 循环遍历 configs.yaml 各厂商 | ⚒️ 需要脚本 |
| CI workflow：repack → upload → docker build → push | 模式已存在于 `flaggems-release.yml` + `runtime.yml` | ⚒️ 需要 workflow |
| app 镜像 Containerfile | `FROM runtime` + pip install vllm + pip install vllm-plugin-FL | ⚒️ 需要 Containerfile |
| 构建后冒烟测试 | `docker run --rm --gpus all <image> python3 -c 'import vllm; ...'` | ⚒️ 需要 CI step |

### 3.2 无法自动化部分

| 任务 | 原因 |
|------|------|
| vllm 版本升级时复查 config.yaml 规则 | 新 vllm 版本可能引入需加入黑名单或 `also_repack` 的新依赖 |
| 判断是否启用 `also_repack` 后备方案 | 只有 pip 解析确实覆盖了 torch 时才需要——需人工检查安装日志 |
| 各平台集成测试 | 各厂商 torch 构建、CUDA ABI、设备特性各不相同 |
| FlagGems 版本升级 + tag | 需与 FlagGems 团队协调 |
| 模型下载 | 环境相关，大文件，需适当存储 |

## 4. 风险与痛点总结

**风险：**

| 风险 | 严重度 | 缓解措施 |
|------|--------|----------|
| vllm 版本升级引入新的黑名单依赖 | 中 | 每次升级检查 METADATA diff，更新 config.yaml |
| 间接依赖声明不兼容的 torch 版本 | 中 | 监控 pip install 输出；also_repack 后备方案存在 |
| pip 解析行为变化 | 低 | 已从 uv 迁移到 pip，pip 稳定性好。pip 升级时重新测试 |
| Vendor PyPI token 过期或更改 | 低 | CI 使用 secrets；文档记录 token 轮换 |
| macOS vs Linux 平台不匹配 | 中 | 永远不在 macOS 上 repack。CI 在 H20 runner 上运行 |
| vllm 二进制 wheel ABI 不兼容 | 低-中 | 警告可接受。生产环境需源码构建 |
| flag_gems 未来又硬锁定其他依赖 | 中 | 已遇到 numpy + sqlalchemy。FlagGems 应用 `>=` 而非 `==` |

**痛点：**

| 痛点 | 严重度 | 备注 |
|------|--------|------|
| 244MB wheel 上传 2-3 min/厂商 | 中 | CI 可接受，14 厂商 ≈ 30 min 可并行 |
| pip 依赖解析慢（vllm 82 个 deps，3-5 min） | 低 | Docker build 中的一次性成本，layer 有缓存 |
| FlagGems 硬锁定依赖级联冲突 | 中 | `sqlalchemy==2.0.48` 装了又被卸载。应审查 FlagGems 其他硬锁定 |
| 节点上无模型文件 | 低 | 每个模型下载一次。使用 `/data/models` 存储 |

`repack_recursive()` 一次性解析 107 个 deps（含 transitive），发现
compressed-tensors (`torch>=1.7.0`) 和 xgrammar (`torch>=1.10.0` +
`triton`)，摘除后输出到 `output/`。无遗漏。

## 5. 设计决策记录

### 5.1 版本号 +flagos 后缀（2026-08-01）

**决策：**
- repack 后的 wheel 统一添加 `+flagos` 本地版本后缀
- 保持原始 platform tag（`py3-none-any`），不伪造为 `cp38-abi3-manylinux_2_35_x86_64`

**理由：**
1. PEP 440 规定：`0.20.2+flagos > 0.20.2`，pip 版本解析应优先选择我们的 repacked wheel
2. 伪造 platform tag 会声明不存在的 ABI 要求，造成误导
3. `+flagos` 明确标识该 wheel 来自 FlagOS repack 流程

**待验证（⚠️）：**

| 验证项 | 状态 | 说明 |
|--------|------|------|
| pip 版本排序行为 | ⬜ | `pip install vllm==0.20.2` 在同时存在 `0.20.2` 和 `0.20.2+flagos` 时，是否一定选择后者？PEP 440 说是，但 pip 实际行为需验证 |
| vendor PyPI + Aliyun 混合索引 | ⬜ | `--index-url vendor --extra-index-url aliyun` 场景下，pip 是否正确解析版本顺序 |
| 缓存干扰 | ⬜ | pip 缓存是否会跳过版本比较，直接复用已下载的 `0.20.2`？ |
| 平台匹配优先级 | ⬜ | 当原版是 `cp38-abi3-manylinux_2_35_x86_64`，我们是 `py3-none-any` 时，平台匹配是否优先于版本比较？ |

**验证方法：**
```bash
# 测试场景：vendor PyPI 有 repacked +flagos，Aliyun 有原版
pip install --index-url $VENDOR_PYPI --extra-index-url $ALIYUN_PYPI vllm==0.20.2
# 检查安装的是哪个版本
pip show vllm
```

**如果验证失败（pip 选择了原版），备选方案：**
1. 版本号改为 `0.20.2.post1`（非本地版本，排序明确高于 `0.20.2`）
2. 或继续使用 platform tag 改写策略（`py3-none-any` → `cp38-abi3-manylinux_2_35_x86_64`）

**相关提交：** TBD (feature/vllm-repack-scripts)

---

### 5.2 vllm repack 包的通用性（待办）

**Empty build** (`VLLM_TARGET_DEVICE=empty`) 是纯 Python，没有硬件特定代码
**Repack** 仅清理 METADATA 依赖声明，不修改代码。输出 platform tag 为 `py3-none-any`，
理论上是通用的。


```
┌─────────────────┐
│  Build vllm     │  ← 任意后端执行 empty build + repack
│  once           │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Upload to ALL  │  ← 同一份 wheel 上传到所有 vendor PyPI
│  vendor PyPIs   │
└─────────────────┘
```

**安装时：**
```bash
# 1. 从任意 vendor PyPI 安装 repacked vllm（通用包）
pip install --no-deps \
  --index-url https://resource.flagos.net/repository/flagos-pypi-mthreads/simple \
  vllm==0.20.2

# 2. 从目标后端 PyPI 安装依赖（获取该后端的 torch 等）
pip install \
  --index-url https://resource.flagos.net/repository/flagos-pypi-hygon/simple \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple \
  vllm==0.20.2
```

**待实现（⬜）：**
1. 修改 `repack-vllm-and-upload.sh` 支持上传到所有 vendor PyPI
2. 或创建通用 workflow：build once → upload to all

**参考：** FlagGems Python 包已采用此工作流（build 一次，上传到所有 vendor PyPI）
