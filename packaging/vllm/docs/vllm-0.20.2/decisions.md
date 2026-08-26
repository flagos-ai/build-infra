# vllm 0.20.2 repack — 流程总结与决策

> 本文对应原报告第 3 部分：自动化边界（§3）、风险与痛点（§4）、ADR（§5）。
> 标准流程见 [`playbook.md`](playbook.md)，后端验证记录见 [`backends/`](backends/)。

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
| 跨后端正式验证矩阵 | ✅ hygon + iluvatar | 两者均直接复用 mthreads 打的 `+flagos` wheel，单步安装零泄漏（[§2.4](backends/hygon.md)、[§2.5](backends/iluvatar.md)）——两次跨后端实证 |

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
出现 aarch64 或别的 pyver 就会静默装入不可用的 `.so`（[§1.3](playbook.md)
已修，tag 真实、pip 按平台选择或明确拒绝）。

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

**已实证（✅ hygon [§2.4](backends/hygon.md)、iluvatar [§2.5](backends/iluvatar.md)）：**
mthreads 上打包上传到 `flagos-pypi-mthreads` 的三个 `+flagos` wheel，在 Hygon
与 iluvatar 上原样单步安装、零 torch/numpy/triton 泄漏（iluvatar 上 wheel
安装本身成功，推理另因厂商工具链过旧受阻，与 wheel 通用性无关）。技术前提
（empty wheel 与后端无关）成立；剩下的是**上传自动化**，非可行性问题。

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
  [vllm-0.24.0 报告](../vllm-0.24.0/index.md)；empty 模式下硬件算子由
  flag_gems（Triton）提供，0.24.0 线上的 NVIDIA 性能结论为全线统一提供了
  同源证据。0.20.2 的 NVIDIA empty 验证接续进行（见
  [§2.1](backends/nvidia.md)）。

**权衡确认：** standard 用 vllm 调优过的 CUDA kernel，通常最快；empty 放弃
这些，换取全线统一与单一可移植 wheel。基准门控撤销后，统一成为明确目标。
