# megatron-builder — megatron-core wheel 工厂验证报告（Facility 1）

> 状态：进行中 —— 首个后端（hygon-dtk26.04）的实测基线已完成，wheel 构建 + 安装验证待跑。
> 本文档是 **Facility 1（wheel 工厂）** 的验证报告，只覆盖 wheel 的构建与实测基线。
> Facility 2（app 镜像自动化：wheel 依赖手术 + 单步安装 + 各后端验证）见
> `megatron-repack/report-megatron-0.17.1.md`。所有数字均为在真实节点/镜像上的
> **实测**，非推断。

## 0. 背景

`megatron-core`（Megatron-LM-FL fork）以 wheel 形式交付。它自带编译扩展
`helpers_cpp`，因此 wheel 是 CPython-ABI 专属的（cp310/cp311/cp312，见 §3）。
fork 的 `pyproject.toml` 声明 `requires-python = ">=3.12"` 和三个运行时依赖（§1）。

**约束（用户确认）：**
- **不用 uv、不用 lock file**（曾被 uv 坑过）。构建走 `pip wheel --no-build-isolation`。
- fork 仓库不动；requires-python 与依赖处理都在 wheel 构建/repack 阶段**现做**。
- 上传目标 `flagos-pypi-hosted`（release 仓库）。

把 wheel 装进 runtime 镜像时是否会破坏精心匹配的 torch/triton 版本矩阵，属于
Facility 2（`megatron-repack/`）的职责——megatron-core 的直接依赖面极小，唯一
真正的风险点是 `torch`，处理方式与 vllm-repack 同类。

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
不用 uv，就用 repack 手段达到等价效果（见 Facility-2 报告 §2.2）。

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

## 3. 构建（已落地，PR #368 合并）

`megatron-builder/Containerfile` 两阶段：

- **toolchain**（`harbor.baai.ac.cn/flagos-dev/megatron-builder-py{310|311|312}`）：
  ubuntu:22.04 + deadsnakes Python + `setuptools<80 wheel pybind11==3.0.3
  numpy==1.26.4 packaging>=24.2`。pybind11/numpy 是 ABI 契约（与 runtime 镜像
  的 pin 对齐）。极少重建。
- **wheel**：`FROM ${BASE_IMAGE}`，clone fork → on-the-fly `requires-python
  >=3.12 → >=3.10`（sed + grep gate）→ 可选版本 stamp → `pip wheel . --no-deps
  --no-build-isolation` → **`.so`-in-wheel gate**（`helpers_cpp*.so` 必须存在，
  防 `optional=True` 静默跳过编译）→ torch-free importlib 冒烟测试。

产物 cp310/cp311/cp312 三个 wheel（`helpers_cpp` 是编译扩展，CPython-ABI 专属）。

**相关文件：** `megatron-builder/Containerfile`、`megatron-builder/README.md`、
`.github/workflows/megatron-builder-image.yml`、`.github/workflows/megatron-wheel.yml`
（均已合并）。Facility-2 依赖手术与验证见
`megatron-repack/report-megatron-0.17.1.md`。
