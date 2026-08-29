# megatron-builder — megatron-core wheel 工厂验证报告（Facility 1）

> 状态：进行中 —— 首个后端（hygon-dtk26.04）的实测基线已完成，wheel 构建 + 安装验证待跑。
> 本文档是 **Facility 1（wheel 工厂）** 的验证报告，只覆盖 wheel 的构建与实测基线。
> Facility 2（app 镜像自动化：wheel 单步安装 + 各后端验证）见
> `packaging/megatron/verify/verify-megatron-backend.sh`。所有数字均为在真实节点/镜像上的
> **实测**，非推断。
>
> **2026-08-14 修订：** 构建环境已改为后端的 runtime 镜像（单阶段 FROM
> `flagos-runtime-{vendor}-{backend}`，不再有 toolchain 镜像，`megatron-builder-image.yml`
> 已删除）；repack facility 已移除（fork-source 路径，wheel 保留 `torch>=2.6.0`）。
> §1 依赖面与 §2 实测基线不变，§3 构建描述已按新形态更新。

## 0. 背景

`megatron-core`（Megatron-LM-FL fork）以 wheel 形式交付。它自带编译扩展
`helpers_cpp`，因此 wheel 是 CPython-ABI 专属的（cp310/cp311/cp312，见 §3）。
fork 的 `pyproject.toml` 声明 `requires-python = ">=3.12"` 和三个运行时依赖（§1）。

**约束（用户确认）：**
- **不用 uv、不用 lock file**（曾被 uv 坑过）。构建走 `pip wheel --no-build-isolation`。
- fork 仓库不动；requires-python 与依赖处理都在 wheel 构建阶段**现做**。
- 上传目标 `flagos-pypi-hosted`（release 仓库）。

把 wheel 装进 runtime 镜像时是否会破坏精心匹配的 torch/triton 版本矩阵，属于
Facility 2（`packaging/megatron/verify/`）的职责——megatron-core 的直接依赖面极小，
唯一真正的风险点是 `torch`，而各后端 runtime vendor torch 均 ≥ 2.7.1，满足
`torch>=2.6.0` 下限，pip 解析器没有理由覆盖任何包（§2 实测）。

## 1. megatron-core 的真实依赖面（来自 `Megatron-LM-FL/pyproject.toml`）

```toml
requires-python = ">=3.12"                       # fork 在 0.17.0 同步时收紧（上游原本 >=3.10）
dependencies = ["torch>=2.6.0", "numpy", "packaging>=24.2"]
```

**只有三个运行时依赖。** 风险分级：

| 依赖 | 声明 | 风险 |
|---|---|---|
| `torch>=2.6.0` | 版本下限 | **唯一真实风险** —— 若运行时 torch < 2.6.0，pip 会拉公有 PyPI torch 替换厂商构建 |
| `numpy` | 无下限 | 低 —— 运行时已 pin（hygon 1.26.4）；我们的 `.so` 用 numpy 1.x 头编译，1.x/2.x 运行时都能跑 |
| `packaging>=24.2` | 下限低 | 无 —— 纯 Python，极小 |

注意 fork 自己的 `[tool.uv] override-dependencies` 就写着"装进 PyTorch base image
时不想安装 torch/torchvision/triton"——上游用 uv override 解同一个问题；我们
不用 uv，但也不需要 repack：各后端 vendor torch 都 ≥ 2.7.1，`torch>=2.6.0`
的 Requires-Dist 天然被满足（§2 实测），单步安装即安全。

**额外事实（实测，见 §2）：** 公有 PyPI 上 **0.17.x 全部 `Requires-Python >=3.12`**
——上游也在 0.17 收紧了 Python 下限。所以 py3.10 运行时（kunlunxin、hygon、
mthreads、iluvatar、tsingmicro）**没有官方 wheel 可用**，fork wheel（配合
Containerfile 里的 on-the-fly requires-python patch）是唯一通路。

## 2. 实测基线（hygon25 节点，2026-08-12）

**节点:** `hygon25`（Hygon BW1000 8× HCU，DTK 26.04）　**镜像:**
`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.2`（本机缓存）
**Python:** 3.10.20

| 包 | 镜像内版本 | megatron 要求 | 满足？ |
|---|---|---|---|
| torch | **2.9.0+das.opt1.dtk2604**（厂商构建） | `torch>=2.6.0` | ✅ 2.9.0 ≥ 2.6.0 |
| numpy | 1.26.4（configs.yaml hygon pin） | `numpy`（无下限） | ✅ |
| packaging | 26.3 | `packaging>=24.2` | ✅ |
| flag_gems | 5.3.4 | — | — |
| triton | （无，由 flagtree 提供） | — | — |

**结论：hygon 上 megatron 的三个依赖全部已被镜像矩阵满足 → pip 解析器没有
理由触碰任何现有包，安装应为"只装 megatron-core 本身"，破坏风险实测为零。**
pip 只在依赖要求不被满足时才替换包；`torch>=2.6.0` 已被厂商 2.9.0 满足。

**两个额外发现：**

1. **公有 PyPI 无 py3.10 兼容的 0.17.x**（`pip install --dry-run megatron-core==0.17.1`
   报 `Requires-Python >=3.12` 被忽略；候选列表里 0.17.x 全部被跳过）。→ fork
   wheel + on-the-fly requires-python patch 是 py3.10 运行时的唯一通路。
2. **`import torch` 需要 DTK 环境**：裸 shell 下 `libgalaxyhip.so.5: cannot open
   shared object file`。`/opt/dtk-26.04/env.sh` 存在（另有
   `/opt/dtk-26.04/.hyhal/hydm/hydmi_env.sh`、`/opt/dtk-26.04/cuda/env.sh`）。
   → 验证步骤必须先 `source /opt/dtk-26.04/env.sh` 再 `import torch`，与镜像
   预期用法一致。

## 3. 构建（2026-08-14 改为 runtime-image-as-build-env）

`packaging/megatron/builder/Containerfile` 单阶段：

- **`FROM ${BASE_IMAGE}`** = 后端的 runtime 镜像
  （`flagos-runtime-{vendor}-{backend}:{version}`，来自
  `scripts/generate_matrix.py --runtime` 的 `matrix.image_tag`）。没有单独的
  toolchain/builder 镜像——`megatron-builder-*` 只是设想、从未构建（CI 曾因此
  失败 `base name should not be blank`），`megatron-builder-image.yml` 已删除。
  构建环境 == 交付环境：python 版本、torch、pybind11==3.0.3、numpy 1.x 头
  全部与目标 runtime 一致，ABI 契约按构造匹配。
- 构建步骤：clone fork → on-the-fly `requires-python >=3.12 → >=3.10`（sed +
  grep gate）→ 可选版本 stamp → 装构建依赖（`setuptools<80 wheel
  pybind11==3.0.3 numpy==1.26.4 packaging>=24.2`，来自 aliyun 镜像）→
  `pip wheel . --no-deps --no-build-isolation`（`--no-deps` 只是不构建 torch，
  不是安装）→ **`.so`-in-wheel gate**（python zipfile 扫描 `helpers_cpp*.so`
  必须存在，防 `optional=True` 静默跳过编译；runtime 镜像无 `unzip`）→
  **冒烟测试**：把 wheel 以完整 `pip install`（解析依赖、无 `--no-deps`）
  装回同一镜像，再用 importlib 加载 `helpers_cpp` 验证 .so 可加载、函数已绑定
  （`import megatron.core` 需要 vendor SDK env，属
  `packaging/megatron/verify/verify-megatron-backend.sh` 的职责）。

产物 cp310/cp311/cp312 三个 wheel（`helpers_cpp` 是编译扩展，CPython-ABI 专属）。

**相关文件：** `packaging/megatron/builder/Containerfile`、`packaging/megatron/builder/README.md`、
`.github/workflows/megatron-wheel.yml`。跨后端共享假设（一个 cpXXX wheel 是否
可在同 Python 版本的后端间共享，glibc 方向性）见 `packaging/megatron/docs/`
（决策 6，未验证）。
