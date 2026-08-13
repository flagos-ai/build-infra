# megatron-repack — megatron app 镜像自动化验证报告（Facility 2）

> 状态：进行中 —— 目录 / Containerfile / config.yaml / 文档已落地（结构先行）；
> 脚本与 workflow 为最小 stub，待 hygon25 验证阶段填充。
> 本文档是 **Facility 2（app 镜像自动化）** 的验证报告。wheel 工厂（构建与实测
> 基线）见 `packaging/megatron/builder/report-megatron-0.17.1.md`。所有数字均为在真实
> 节点/镜像上的**实测**，非推断。

## 0. 背景

megatron 工作分两个 facility：

- **Facility 1 — wheel 工厂**（`packaging/megatron/builder/`，仿 `packaging/flaggems/`）：
  产出可安装的 megatron-core wheel。**已完成**（PR #368），见其报告。
- **Facility 2 — app 镜像自动化**（本目录 + `app/megatron/Containerfile` +
  `.github/workflows/megatron-app-image.yml`）：把 wheel 装进
  `flagos-runtime-{vendor}-{backend}` 镜像，产出 app 镜像。vllm 的对应物是
  `packaging/vllm/` + `app/vllm/Containerfile`。**本报告即此 facility 的设计与待办。**

把 wheel 装进镜像时，若其 METADATA 的 `Requires-Dist` 与镜像内**精心匹配、反复
验证过的版本矩阵**（厂商 torch / triton / flagtree / flag_gems / numpy）冲突，
pip 解析器可能**替换或升级**其中的包，破坏整个运行时栈——与 vllm-repack 要解决的
问题同类。与 vllm 不同的是，megatron-core 的**直接依赖面极小**（torch / numpy /
packaging 三项，见 Facility-1 报告 §1），不需要 vllm 那套复杂的分类器，只需要
针对唯一真正的风险点——`torch`——做精确处理。

**约束（用户确认）：**
- **不 brutal 地全剥依赖**（`pip install --no-deps` 被用户否决——"I'm always
  worrisome about --no-deps, it breaks everything"）。要做的是"检测它是否会
  破坏精心构建的 torch/triton 矩阵"，与 vllm-repack 同一思路，通过 repack
  wheel METADATA 实现（§2.2）。
- repack **复用** `packaging/vllm/repack.py`（通用手术工具，该目录承载用户的
  未提交修改——**只读引用，不复制不修改**）。
- 安装是 vendor 为主索引的单步 `pip install`（无 `--no-deps`）。
- fork 仓库不动；requires-python 与依赖处理都在 wheel 构建/repack 阶段**现做**。

## 1. 破坏风险矩阵（各后端）

| 后端 | 运行时 torch | 风险 |
|---|---|---|
| hygon-dtk26.04 | 2.9.0+das.opt1.dtk2604 | ✅ 无（2.9.0 ≥ 2.6.0） |
| mthreads / metax / nvidia / ... | 待各节点实测 | ⬜ 待测 |
| **任意 torch < 2.6.0 的后端** | 未知 | 🔴 pip 会拉公有 torch 替换厂商构建 → 必须靠 METADATA 处理（§2.2） |

**结论：** "今天安全"依赖 torch 版本不下滑；"永远安全"要靠 §2.2 的 repack 把
torch 声明从 wheel METADATA 里去掉/钉死——这正是 vllm-repack `remove_torch_chain`
的思路。megatron 只需处理 torch 一项。

## 2. 设计（依赖安全处理）

### 2.1 构建（Facility 1，已落地）

wheel 的构建、on-the-fly requires-python patch、`.so`-in-wheel gate、冒烟测试
都在 `packaging/megatron/builder/`（PR #368 合并），详见 Facility-1 报告 §3。产物
cp310/cp311/cp312 三个 wheel（`helpers_cpp` 是编译扩展，CPython-ABI 专属）。

### 2.2 依赖处理（repack，仿 vllm-repack）

现状：Containerfile/README 曾写 `pip install --no-deps` —— **被用户否决**。方向
改为 vllm-repack 模式：

- 对 Facility-1 产出的 wheel 做 repack：剥掉 `Requires-Dist: torch>=2.6.0`（或
  钉成 `==<厂商 torch 版本>`），`+flagos` 后缀，`.deps-manifest.yaml` 记录
  removed/retained，Metadata-Version 2.4→2.2。
- 分类规则 `packaging/megatron/repack/config.yaml`（torch 是唯一真实风险）：
  ```yaml
  remove_torch_chain: [torch]
  remove_cuda_only: []
  remove_orphaned: []
  strip_from_indirect: [torch, triton]
  strip_extra_from_indirect: {}
  ```
- 安装命令变为 vendor 为主索引的单步安装（无 `--no-deps`）：
  ```
  pip install megatron-core==0.17.1+flagos \
    --index-url https://resource.flagos.net/repository/flagos-pypi-<vendor>/simple \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple
  ```
- 验证：before/after 快照对比 torch/triton/flag_gems/numpy 版本**逐项相等**，
  再 `import megatron.core` 确认 `helpers_cpp` 载入（镜像上先 `source
  /opt/dtk-26.04/env.sh`）。

## 3. 待办

| 事项 | 状态 |
|---|---|
| packaging/megatron/repack/ 结构（config.yaml + 脚本/ workflow stub） | ✅ 本报告 |
| app/megatron/Containerfile | ✅ |
| 文档 docs/content/{zh-cn,en}/application/megatron.md | ✅ |
| hygon25 上构建 Facility-1 wheel（py3.10, x86_64） | ⬜ |
| 填充 build-and-repack.sh + verify-megatron-backend.sh + workflow | ⬜ |
| repack（剥 torch、+flagos、manifest） | ⬜ |
| runtime 容器内单步安装 + before/after 快照对比 | ⬜ |
| `import megatron.core` + `helpers_cpp` 确认 | ⬜ |
| 其余后端（mthreads/metax/... 节点恢复后）逐栈验证 | ⬜ |
| 上传 `flagos-pypi-hosted`（用户申请上传权限中） | ⬜ |

**相关文件：** `packaging/megatron/repack/config.yaml`、`packaging/megatron/repack/build-and-repack.sh`
（stub）、`packaging/megatron/repack/verify-megatron-backend.sh`（stub）、
`app/megatron/Containerfile`、`.github/workflows/megatron-app-image.yml`（stub）。
vllm-repack 模式参考：`packaging/vllm/repack.py` + `config.yaml` + `build-and-repack.sh`
+ `verify-vllm-backend.sh`。wheel 工厂参考：`packaging/megatron/builder/Containerfile` +
`packaging/megatron/builder/report-megatron-0.17.1.md`。
