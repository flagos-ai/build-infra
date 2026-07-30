# vllm-repack — 端到端验证报告

## 1. NVIDIA cuda12.8

**日期:** 2026-07-27/28  
**平台:** NVIDIA H20 (8×)  
**目标:** vllm 0.20.2 + vllm-plugin-FL, flagos-runtime-nvidia-cuda12.8:2.1.1

---

### 1.1 设计决策（Phase 0）

用户给出了三条关键约束：

1. **不使用 `.post1` 后缀** — uv 时代的反升级 trick，pip 下不再需要
2. **PyPI 分离** — vendor PyPI 只放 repacked vllm wheel（1 个文件）。其余 deps 从 Aliyun 拉。不托管间接依赖的 repack 版本，维护成本太大
3. **保留 deps 安装，不用 `--no-deps`** — repacked wheel 保留除黑名单外的所有 Requires-Dist。

### 1.2 repack.py 改动（Phase 1）

#### 1.2a 去掉 `.post1` 后缀

**文件:** `vllm-repack/repack.py`  
**改动:** `VERSION_SUFFIX = ""`（原来 `".post1"`）

设空后 `_bump_version()` 和 `_bump_dist_info_dir()` 成为空操作——
repacked wheel 保持原始版本。pip 通过 `--extra-index-url` 从 vendor
PyPI 安装，与上游同版本即可匹配。

#### 1.2b 默认索引改为 Aliyun 镜像

**文件:** `vllm-repack/repack.py`  
**改动:** `https://pypi.org/simple/` → `https://mirrors.aliyun.com/pypi/simple/`

节点无法访问 pypi.org，所有下载走 Aliyun。

#### 1.2c 保留 `also_repack` 在 Requires-Dist 中

**文件:** `vllm-repack/repack.py`  
**改动:** `also_repack` 包原分类为 `"repack"`，会从 vllm 的 Requires-Dist
中删除并单独 repack。现在分类为 `"keep"`——保留其 Requires-Dist 行，
pip 从 Aliyun 自然解析。

`repack_indirect()` 逻辑保留作为后备：如果间接依赖锁定了不兼容的
torch 版本，可手动调用。

#### 1.2d 修复 METADATA 空行 bug（关键修复）

**文件:** `vllm-repack/repack.py`，函数 `_downgrade_metadata_version`

**Bug:** 为 Metadata-Version 2.4→2.2 降级时，删除 `License-File` 和
`Dynamic:` 行的正则替换留下了一个空行。在 email 格式的 METADATA 中，
第一个空行标记 headers 结束。该空行之后的所有 Requires-Dist 行对 pip
不可见。

**修复:** 正则加上 `\n?` 吃掉尾随换行：
```python
# 修复前（broken）:
_LICENSE_FILE_RE = re.compile(r"^License-File:\s*.+$", re.M)
_DYNAMIC_RE = re.compile(r"^Dynamic:\s*.+$", re.M)

# 修复后（fixed）:
_LICENSE_FILE_RE = re.compile(r"^License-File:\s*.+\n?", re.M)
_DYNAMIC_RE = re.compile(r"^Dynamic:\s*.+\n?", re.M)
```

这是"METADATA 中所有依赖都存在但 pip 看不到"的根本原因。

#### 1.2e 更新模块文档字符串

反映新设计（2026-07-27）。

### 1.3 configs.yaml 改动（Phase 2）

#### 1.3a 升级 flag_gems 版本

```yaml
# 修改前:
flaggems: "5.3.1"
# 修改后:
flaggems: "5.3.2"
```

#### 1.3b 升级 numpy 版本（并在 FlagGems 中放宽限制）

```yaml
# 修改前:
runtime_prereqs:
  - "numpy==1.26.4"
# 修改后:
runtime_prereqs:
  - "numpy==2.3.5"
```

背景：vllm 依赖 `opencv-python-headless>=4.13.0` 声明
`numpy>=2; python_version >= "3.9"`，runtime 中 `numpy==1.26.4`
不兼容。全 14 个后端中没有 vendor torch 声明 `numpy<2`。

### 1.4 FlagGems 改动（Phase 3，独立仓库）

**文件:** `FlagGems/pyproject.toml`  
**改动:** `"numpy==1.26.4"` → `"numpy"`（不锁定版本）  
**Tag:** `v5.3.2`

### 1.5 构建、上传、安装、验证（Phase 4）

#### 1.5a 下载 vllm wheel

```bash
# 在 Linux x86_64 目标机器上（非 macOS！）
pip download --no-deps --dest /tmp/vllm-dl "vllm==0.20.2" \
  --index-url https://mirrors.aliyun.com/pypi/simple
```

#### 1.5b Repack

```bash
python3 vllm-repack/repack.py /tmp/vllm-dl/vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl
```

结果：7 个黑名单依赖移除，82 个保留，6 个 also_repack 候选保留。

#### 1.5c 上传 repacked wheel 到 vendor PyPI

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-nvidia/ \
  /tmp/vllm-repack/output/vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl
```

#### 1.5d 安装流程

```bash
# 1. 运行时依赖（torch, flagtree, flag_gems, ...）
pip install \
  --index-url https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple \
  torch==2.10.0+cu128 torchaudio==2.10.0+cu128 torchvision==0.25.0+cu128 \
  flagtree==0.6.0 flag_gems==5.3.2 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.1 numpy==2.3.5

# 2. vllm（repacked，不用 --no-deps！）
pip install \
  --index-url https://mirrors.aliyun.com/pypi/simple \
  --extra-index-url https://resource.flagos.net/repository/flagos-pypi-nvidia/simple \
  vllm==0.20.2

# 3. vllm-plugin-FL（源码构建）
git clone https://github.com/flagos-ai/vllm-plugin-FL
cd vllm-plugin-FL
VLLM_VENDOR=cuda pip install --no-build-isolation .
```

**关键心得：** flag_gems 绝不能 `--no-deps`——它的 `sqlalchemy==2.0.48`
依赖需要从 Aliyun 拉取。

#### 1.5e 启动 vllm serve

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

#### 1.5f 测试推理

```json
{"model":"qwen","choices":[{"message":{"content":"Here's a thinking process:\n\n1.  **Analyze User Input:**..."}}]}
{"usage":{"prompt_tokens":17,"total_tokens":145,"completion_tokens":128}}
```

✅ 推理成功。

---

### 1.6 遇到的 Bug 及根因

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | `pip install repacked-vllm.whl` → vllm import 失败：`ModuleNotFoundError: No module named 'regex'` | METADATA header 在 `License-File` 删除留下的空行处截断。后面 82 行 Requires-Dist 对 pip 不可见 | 正则加 `\n?` 吃掉尾随换行 |
| 2 | `pip install` 升级 numpy 1.26.4 → 2.3.5，flag_gems 崩溃 | `opencv-python-headless` 声明 `numpy>=2`，flag_gems 声明 `numpy==1.26.4` | 放宽 FlagGems `pyproject.toml` 为 `numpy` 不锁定；configs.yaml 改为 `2.3.5` |
| 3 | vllm 安装后 `sqlalchemy` 完全消失 | flag_gems 用了 `--no-deps`，其依赖未拉取。vllm 解析不需要 sqlalchemy → 被卸载 | 安装 flag_gems 不用 `--no-deps` |
| 4 | macOS `pip download vllm==0.20.2` 拿到 sdist，version: 0.20.2+cpu → 版本不一致 | macOS 无 manylinux wheel；Aliyun 只提供 sdist | 始终在目标 Linux x86_64 节点上操作，不要用 macOS |
| 5 | `vllm serve` 警告 `_C.abi3.so: undefined symbol: _ZN3c1013MessageLoggerC1E...` | vllm 二进制 wheel 与主机 CUDA 的 ABI 不匹配——非致命，C 扩展优雅降级 | PoC 可接受。生产环境需用匹配 CUDA 版本编译 vllm |

---

### 1.7 架构：各组件去向

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

---

### 1.8 可自动化部分

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

### 1.9 无法自动化部分

| 任务 | 原因 |
|------|------|
| vllm 版本升级时复查 config.yaml 规则 | 新 vllm 版本可能引入需加入黑名单或 `also_repack` 的新依赖 |
| 判断是否启用 `also_repack` 后备方案 | 只有 pip 解析确实覆盖了 torch 时才需要——需人工检查安装日志 |
| 各平台集成测试 | 各厂商 torch 构建、CUDA ABI、设备特性各不相同 |
| FlagGems 版本升级 + tag | 需与 FlagGems 团队协调 |
| 模型下载 | 环境相关，大文件，需适当存储 |

### 1.10 待提交的改动

**build-infra（本仓库）：**

| 文件 | 改动 | PR? |
|------|------|-----|
| `vllm-repack/repack.py` | VERSION_SUFFIX=""、Aliyun 默认索引、also_repack 保留、空行正则修复、文档字符串更新 | 是 |
| `configs.yaml` | `flaggems: "5.3.2"`、`numpy==2.3.5` | 是 |

**FlagGems（独立仓库）：**

| 文件 | 改动 | 状态 |
|------|------|------|
| `pyproject.toml` | `"numpy==1.26.4"` → `"numpy"`（不锁定） | 已 tag `v5.3.2` |

**新建文件：**

| 文件 | 用途 |
|------|------|
| `scripts/repack_vllm.py` | 下载 vllm wheel → repack → twine upload 到所有 vendor PyPI |
| `app/vllm/Containerfile` | FROM runtime → pip install vllm + vllm-plugin-FL |
| `.github/workflows/vllm-app.yml` | 完整 CI：repack → upload → build → verify → push |

---

### 1.11 风险与痛点

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
| SSH 网关不稳定 | 高 | 约 50% 尝试出现 `no available gateway` |
| 244MB wheel 上传 2-3 min/厂商 | 中 | CI 可接受，14 厂商 ≈ 30 min 可并行 |
| pip 依赖解析慢（vllm 82 个 deps，3-5 min） | 低 | Docker build 中的一次性成本，layer 有缓存 |
| FlagGems 硬锁定依赖级联冲突 | 中 | `sqlalchemy==2.0.48` 装了又被卸载。应审查 FlagGems 其他硬锁定 |
| 节点上无模型文件 | 低 | 每个模型下载一次。使用 `/data/models` 存储 |

---

### 1.12 完整 Stack 验证（nvidia-cuda12.8）

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

### 1.13 后续步骤（NVIDIA）

1. **Commit + PR** `repack.py` + `configs.yaml` 改动到 build-infra
2. **构建和发布** flag_gems 5.3.2 wheels 到全部 vendor PyPI
3. **编写** `scripts/repack_vllm.py` 做 CI 自动化
4. **编写** `app/vllm/Containerfile`
5. **扩展到 nvidia-cuda13.3**（相同模式，不同 torch 版本）
6. **多厂商铺开** — metax, hygon, iluvatar, mthreads, kunlunxin, cambricon（CUDA 路线）

---

## 2. MetaX maca3.7.2.1

**日期:** 2026-07-28/29  
**平台:** MetaX C550 (8×, 64GB)  
**节点:** metax124 (bm-zksg-wx-zone1-d-mc550-64g-2-124)  
**MACA:** 3.7.2.0, Driver 3.8.30  
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL, flagos-runtime-metax-maca3.7.2.1:2.1.1

### 2.1 核心结论：必须用 empty 构建

MetaX MACA 没有 NVIDIA CUDA 扩展——vllm 标准 wheel 中的
`_C.abi3.so`、`_moe_C.abi3.so` 是为 NVIDIA GPU 编译的，
无法在 MACA 上加载。`vllm serve` 启动即崩溃：

```
AttributeError: '_OpNamespace' '_C_cache_ops' object has no
  attribute 'reshape_and_cache_flash'
```

必须用 **empty 构建**（`VLLM_TARGET_DEVICE=empty`）编译不含硬件
kernel 的 vllm。除此之外，repack 规则、间接依赖处理、
vllm-plugin-FL 安装均与 NVIDIA 相同。

### 2.2 编译 empty vllm wheel

```bash
cd /workspace/vllm                      # 节点上已有的 v0.20.2 源码
VLLM_TARGET_DEVICE=empty MAX_JOBS=64   \
pip wheel --no-build-isolation --no-deps -w /tmp/empty .
# → vllm-0.20.2+empty-py3-none-any.whl (6.3 MB, 无 .so 文件)
```

### 2.3 Repack（去掉 `+empty` 本地版本、修复平台 Tag）

与 NVIDIA 流程相比，repack.py 需增加三项处理：

1. **去掉 METADATA 中 `Version:` 的 `+empty` 后缀** — PEP 440 本地版本
   不会被 `pip install vllm==0.20.2` 匹配
2. **重命名 `.dist-info` 目录** — `vllm-0.20.2+empty.dist-info`
   → `vllm-0.20.2.dist-info`
3. **改写 `WHEEL Tag:`** — `py3-none-any` →
   `cp38-abi3-manylinux_2_35_x86_64`，防止 pip 因平台匹配度
   优先选择 Aliyun 上的原版 wheel

```bash
python3 vllm-repack/repack.py /tmp/empty/vllm-0.20.2+empty-py3-none-any.whl
# → vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl
#   Version: 0.20.2, 77 行 Requires-Dist, Metadata-Version 2.2
```

以上改动（`_strip_local_version`、`_VLLM_PLATFORM_TAG`、
`_WHEEL_TAG_RE`、`_rewrite_wheel_impl` 目录重命名逻辑）待 commit。

### 2.4 上传到 metax PyPI

```bash
twine upload -u flagos -p '<token>' \
  --repository-url https://resource.flagos.net/repository/flagos-pypi-metax/ \
  repacked-wheel.whl
```

### 2.5 递归间接依赖 repack

**Note (2026-07-30):** 本节原记录了 6 个间接依赖，但那是基于标准 vllm wheel
的 Requires-Dist — 标准 wheel 包含 `flashinfer-python`、`quack-kernels`、
`tilelang` 等。empty 构建（`VLLM_TARGET_DEVICE=empty`）跳过了这些硬件加速
后端，所以 empty vllm 实际上只有 **2 个**间接依赖声明了 torch/triton。

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

### 2.6 安装流程

```bash
VENDOR=https://resource.flagos.net/repository/flagos-pypi-metax/simple
ALIYUN=https://mirrors.aliyun.com/pypi/simple

# 1. 运行时依赖（与 CUDA 一致：vendor 为主，Aliyun 补充）
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" \
  torch==2.8.0+metax3.7.2.0 torchaudio==2.4.1+metax3.7.2.0 \
  torchvision==0.15.1+metax3.7.2.0 flash_attn==2.6.3+metax3.7.2.0torch2.8 \
  flagtree==3.1.0+metax3.7.2.0 triton==3.0.0+metax3.7.2.0 flag_gems==5.3.2 \
  pybind11==3.0.3 ninja==1.13.0 PyYAML==6.0.3 numpy==2.3.5

# 2. vllm — 分两步（MetaX 专属：vendor torch 版本 < Aliyun torch）
pip install --no-deps --index-url "$VENDOR" vllm==0.20.2   # ① 锁定 repacked empty
pip install --index-url "$ALIYUN" vllm==0.20.2             # ② 补全 safe deps

# 3. vllm-plugin-FL — 纯 Python，不设 VLLM_VENDOR
cd /workspace/vllm-plugin-FL
pip install --no-build-isolation -e .
```

**为什么分两步？** `torch-2.8.0+metax3.7.2.0` 在 PEP 440 中排序低于
`torch-2.11.0`（本地版本号排在基础版本号之下）。一步安装 `pip install
--index-url $VENDOR --extra-index-url $ALIYUN vllm` 会触发 torch 降级。
先用 `--no-deps` 锚定 repacked vllm，再补全 safe deps，torch 不变。

### 2.7 vllm-plugin-FL 需要修复的两个问题

在 MetaX 上跑 empty vllm 时，vllm-plugin-FL 的 metax vendor backend
有两处需修改：

| # | 现象 | 根因 | 修复 | PR |
|---|---|---|---|---|
| 1 | `_C_cache_ops.reshape_and_cache_flash` AttributeError | MetaX flash attn 后端调用 `vllm._custom_ops.reshape_and_cache_flash` → `torch.ops._C_cache_ops.*`——empty 构建不编译此模块 | `patches/__init__.py` 中 patch：路由到 vllm 内置的 Triton 纯 Python 实现（`triton_reshape_and_cache_flash`） | [#319](https://github.com/flagos-ai/vllm-plugin-FL/pull/319) |
| 2 | `_C.silu_and_mul` AttributeError | `silu_and_mul_maca` 实例化 `SiluAndMul()`，其 `__init__` 访问 `torch.ops._C.silu_and_mul`——在模型加载阶段崩溃，dispatch 来不及介入 | 用 `F.silu` / `F.gelu` 替换 `SiluAndMul()` / `GeluAndMul()`——功能等价，不依赖 `_C` | [#325](https://github.com/flagos-ai/vllm-plugin-FL/pull/325) |

**第 2 个问题是最微妙的。** 崩溃发生在 `__init__`，不是 `forward`。
vllm_fl 的分发层（`forward_oot → call_op → flagos/vendor/reference`）
只在实际推理时生效——但 `__init__` 在模型加载阶段运行，dispatch 来不及拦截：

```
vllm/model_executor/models/qwen3.py:204 Qwen3DecoderLayer.__init__()
  → qwen2.py:111 lambda 初始化
    → vllm_fl/ops/activation.py:10 SiluAndMulFL.__init__()
      → super().__init__()       # vllm SiluAndMul.__init__
        → activation.py:133 self.op = torch.ops._C.silu_and_mul  💥
```

### 2.8 启动 vllm serve

```bash
export MACA_PATH=/opt/maca
export PATH=/opt/maca/mxgpu_llvm/bin:/opt/maca/bin:$PATH
export LD_LIBRARY_PATH=/opt/maca/lib:/opt/maca/mxgpu_llvm/lib
export GEMS_VENDOR=metax
export VLLM_PLUGINS=fl
export MACA_VISIBLE_DEVICES=4

vllm serve /data/models/Qwen/Qwen3-4B --port 8031 \
  --gpu-memory-utilization 0.5 --enforce-eager \
  --trust-remote-code --max-model-len 2048
```

### 2.9 测试推理

```json
{"choices":[{"message":{"content":"你好！..."}}],
 "usage":{"prompt_tokens":9,"completion_tokens":32}}
```

✅ MetaX C550 + empty vllm 推理成功。

### 2.10 与 NVIDIA CUDA 后端的差异

| 步骤 | NVIDIA cuda12.8 | MetaX maca3.7.2.1 |
|---|---|---|
| vllm wheel | 标准版 — 从 Aliyun 下载 | **empty 构建**（`VLLM_TARGET_DEVICE=empty`） |
| repack 额外处理 | 无 | 去掉 `+empty` 版本后缀、修复 WHEEL Tag |
| vendor deps | torch/cu128, triton 3.6.0 | torch/metax, flash_attn/metax, triton 3.0.0 |
| vllm 安装 | 一步 `pip install` | 两步：先 `--no-deps` 锁定，再补 deps |
| vllm-plugin-FL | `VLLM_VENDOR=cuda` 编译 C 扩展 | 不设 VLLM_VENDOR，额外需 PR #319 + #325 |
| 间接依赖 repack | 相同的 6 个包 | 相同 |

### 2.11 完整 Stack 验证

```
torch:        2.8.0+metax3.7.2.0    ✅  from vendor PyPI
torchaudio:   2.4.1+metax3.7.2.0    ✅
torchvision:  0.15.1+metax3.7.2.0   ✅
flash_attn:   2.6.3+metax3.7.2.0    ✅  MetaX flash attention
flagtree:     3.1.0+metax3.7.2.0    ✅  默认编译器
triton:       3.0.0+metax3.7.2.0    ✅
flag_gems:    5.3.2                 ✅  use_gems() OK
vllm:         0.20.2                ✅  empty, repacked, vendor PyPI
vllm_fl:      loaded                ✅  纯 Python, PR #319 + #325
MACA:         True                  ✅  mx-smi, torch.cuda.is_available()
Inference:    Qwen3-4B              ✅  9→32 tokens, flash attention
```

### 2.12 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| vllm-plugin-FL PR #319 | 🔄 审核中 | `_C_cache_ops` Triton fallback |
| vllm-plugin-FL PR #325 | 🔄 审核中 | `silu_and_mul_maca` / `gelu_and_mul_maca` → F.silu/F.gelu |
| repack.py 改动 commit | ✅ | empty-wheel 支持 + 递归审计，见 PR #244 #247 + commit 169e5ef |
| 间接 repack 自动化 | ✅ | `repack_recursive()` 自动发现 + repack，见 §2.13 |
| FlagGems pyproject.toml | ⬜ | build-system.requires 加 `wheel==0.45.0` |
| 更大模型测试 | ⬜ | 仅测过 Qwen3-4B；27B、35B-A3B 待测 |
| graph 模式测试 | ⬜ | 仅 eager 模式 |
| 其他 empty 模式后端 | 🔄 | hygon 进行中；kunlunxin、iluvatar、mthreads 待排队 |

### 2.13 构建容器可重现 repack (2026-07-30)

使用 `flagos-runtime-metax-maca3.7.2.1:2.1.1-build` 镜像作为构建
环境（torch 2.8.0+metax、Python 3.12、uv、setuptools-scm 全部就绪），
确保 empty vllm 编译环境与 runtime 完全一致。

**流程：**

```bash
# 1. 基于 build 镜像起容器
docker run -d --name vllm-build-metax --network host \
  -v /tmp/vllm-repack:/tmp/vllm-repack \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.7.2.1:2.1.1-build \
  sleep infinity

# 2. 装 setuptools-scm（一次性，build 镜像可能需要更新）
docker exec vllm-build-metax bash -lc \
  'pip install -i https://mirrors.aliyun.com/pypi/simple setuptools-scm'

# 3. 编译 empty vllm
docker exec vllm-build-metax bash -lc '
  cd /tmp/vllm && git checkout v0.20.2
  VLLM_TARGET_DEVICE=empty MAX_JOBS=64 \
    pip wheel --no-build-isolation --no-deps -w /tmp/empty .
'

# 4. 运行 repack_recursive
docker exec vllm-build-metax bash -lc '
  cd /tmp/vllm-repack
  python3 repack.py /tmp/empty/vllm-0.20.2+empty-py3-none-any.whl
'
```

**结果：**

| 文件 | sha256 |
|------|--------|
| empty vllm wheel | `29afd59aae76d41d05fea3f93279a2b5fe9a8d607b990f1e4b1ecd0f80390887` |
| repacked vllm | `vllm-0.20.2-cp38-abi3-manylinux_2_35_x86_64.whl` (6.5MB) |
| repacked compressed-tensors | `compressed_tensors-0.15.0.1-py3-none-any.whl` (190KB) |
| repacked xgrammar | `xgrammar-0.2.3-py3-none-any.whl` (43MB) |

`repack_recursive()` 一次性解析 107 个 deps（含 transitive），发现
compressed-tensors (`torch>=1.7.0`) 和 xgrammar (`torch>=1.10.0` +
`triton`)，摘除后输出到 `output/`。无遗漏。

**直接安装验证：**

```bash
# 将 repacked wheels 上传到 metax PyPI 后
pip install --no-deps --index-url $METAX_PYPI vllm==0.20.2
pip install --index-url $ALIYUN vllm==0.20.2
pip install vllm-plugin-FL
# → torch 保持 2.8.0+metax3.7.2.0，triton 保持 3.0.0+metax3.7.2.0
```

**注：** 此流程对未来的工作流设计具有参考意义 — build 镜像已固化完整
编译环境，`repack_recursive()` 实现全自动依赖审计，两种机制结合可实现
跨所有空模式后端的 CI 自动化。
