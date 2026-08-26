# Megatron 场景 × 编译器 × 后端 验证矩阵

> **原则：上游 PR 不自 merge，review 期间用 PR head 推进制品。**
> 提给上游仓库的 PR 由各自维护团队合并。
> 为保证 review 期间不阻塞，用 PR head 构建 wheel → 验证 → 打镜像（版本指向
> PR head commit）；PR 合并后重走一遍流程产出定稿制品。中间 PR-head 制品只用于
> 推进验证，不作为发布件。

> 规划工具，随验证推进更新。每单元格为对应后端 runtime 镜像 + 一步安装 wheel 后，对应场景入口跑通的验证。
> wheel 打包范围：core+training+legacy+rl+post_training+inference（全范围
> wheel，[MLF PR #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) feat/wheel-full-scope）；hygon/nvidia/metax/ascend
> 均已用该 wheel 验证（详见厂商文档）。

## 状态图例

| 符号 | 含义 |
|---|---|
| ✅ | 已验证通过（E2E exit 0） |
| ❌ | 已屏蔽（编译器不可用，不设默认/不交付） |
| ⛔ | 挂起（需先解决上游阻塞） |
| ？ | 成功概率不确定（缺 vendor 变体依赖） |
| ⬜ | 待验证 |
| — | 该后端无此编译器 |

列名后缀：T = Triton 编译器，F = FlagTree 编译器。

> 注：各编译器在对应后端的具体版本、前置与 workaround（hygon jit_fuser
> 补丁、ascend torch-first 导入顺序、nvidia inductor fork 规避等）见厂商
> 文档：[[megatron-hygon25-e2e.md]] / [[megatron-nvidia-e2e.md]] /
> [[megatron-ascend-e2e.md]] / [[megatron-metax-e2e.md]]。

## 矩阵

<!-- status-matrix:verification -->

| 厂商 | 后端 | 训练(T) | 训练(F) | 强化学习(T) | 强化学习(F) | 后训练(T) | 后训练(F) | 推理(T) | 推理(F) |
|---|---|---|---|---|---|---|---|---|---|
| 英伟达 | CUDA 12.8 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 英伟达 | CUDA 13.3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 昇腾 | CANN 8.5.0 | ✅ | ✅ | ⛔ | ⛔ | ✅ | ✅ | ✅ | ✅ |
| 昇腾 | CANN 9.0.0 | ✅ | ✅ | ⛔ | ⛔ | ✅ | ✅ | ✅ | ✅ |
| 寒武纪 | NEUWARE 4.4.3 | ✅ | — | ⛔ | — | ✅ | — | ✅ | — |
| 寒武纪 | NEUWARE 4.7.2 | ✅ | — | ⛔ | — | ✅ | — | ✅ | — |
| 燧原 | TOPS 1.9.10 | ⬜ | ⬜ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |
| 燧原 | TOPS 1.10.6 | ⬜ | ⬜ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |
| 海光 | DTK 26.04 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 天数智芯 | COREX 4.4.0 | ⬜ | ⬜ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |
| 昆仑芯 | XRE 5.37.1 | ⬜ | ⬜ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |
| 沐曦 | MACA 3.7.2.1 | ✅ | ✅ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |
| 沐曦 | MACA 3.8.1.3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 摩尔线程 | MUSA 4.3.6 | ⬜ | ⬜ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |
| 摩尔线程 | MUSA 5.2.0 | ✅ | ✅ | ⛔ | ⛔ | ✅ | ✅ | ✅ | ✅ |
| 进迭时空 | SPACEMIT | ⬜ | — | ⛔ | — | ？ | — | ⛔ | — |
| 曦望 | TANGRT 1.2.0 | ⬜ | ⬜ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |
| 平头哥 | PPU 2.0.0 | ⬜ | — | ⛔ | — | ？ | — | ⛔ | — |
| 清微智能 | TSM 260610 | ⬜ | ⬜ | ⛔ | ⛔ | ？ | ？ | ⛔ | ⛔ |

**后端级上游 PR（验证/镜像基于 PR 分支 Head 的跟踪项）**

| 厂商 | 后端 | App | PR |
|---|---|---|---|
| 英伟达 | CUDA 12.8 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/107 |
| 英伟达 | CUDA 12.8 | megatron_training | https://github.com/NVIDIA/Megatron-LM/pull/34 |
| 英伟达 | CUDA 12.8 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/120 |
| 英伟达 | CUDA 12.8 | megatron_training | https://github.com/NVIDIA/Megatron-LM/pull/6709 |
| 英伟达 | CUDA 12.8 | megatron_rl | https://github.com/flagos-ai/Megatron-LM-FL/pull/114 |
| 英伟达 | CUDA 12.8 | megatron_rl | https://github.com/flagos-ai/Megatron-LM-FL/pull/119 |
| 英伟达 | CUDA 12.8 | megatron_rl | https://github.com/NVIDIA/Megatron-LM/pull/6709 |
| 英伟达 | CUDA 13.3 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/107 |
| 英伟达 | CUDA 13.3 | megatron_training | https://github.com/NVIDIA/Megatron-LM/pull/34 |
| 英伟达 | CUDA 13.3 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/120 |
| 英伟达 | CUDA 13.3 | megatron_training | https://github.com/NVIDIA/Megatron-LM/pull/6709 |
| 英伟达 | CUDA 13.3 | megatron_rl | https://github.com/flagos-ai/Megatron-LM-FL/pull/114 |
| 英伟达 | CUDA 13.3 | megatron_rl | https://github.com/flagos-ai/Megatron-LM-FL/pull/119 |
| 英伟达 | CUDA 13.3 | megatron_rl | https://github.com/NVIDIA/Megatron-LM/pull/6709 |
| 昇腾 | CANN 8.5.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/107 |
| 昇腾 | CANN 8.5.0 | megatron_training | https://github.com/flagos-ai/FlagTree/pull/1023 |
| 昇腾 | CANN 8.5.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/124 |
| 昇腾 | CANN 8.5.0 | megatron_training | https://github.com/flagos-ai/FlagTree/pull/1025 |
| 昇腾 | CANN 9.0.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/107 |
| 昇腾 | CANN 9.0.0 | megatron_training | https://github.com/flagos-ai/FlagTree/pull/1023 |
| 昇腾 | CANN 9.0.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/124 |
| 昇腾 | CANN 9.0.0 | megatron_training | https://github.com/flagos-ai/FlagTree/pull/1025 |
| 寒武纪 | NEUWARE 4.4.3 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/125 |
| 寒武纪 | NEUWARE 4.7.2 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/125 |
| 海光 | DTK 26.04 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/122 |
| 海光 | DTK 26.04 | megatron_rl | https://github.com/flagos-ai/Megatron-LM-FL/pull/114 |
| 沐曦 | MACA 3.8.1.3 | megatron_rl | https://github.com/flagos-ai/Megatron-LM-FL/pull/114 |
| 沐曦 | MACA 3.8.1.3 | megatron_rl | https://github.com/flagos-ai/Megatron-LM-FL/pull/116 |
| 摩尔线程 | MUSA 5.2.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/105 |
| 摩尔线程 | MUSA 5.2.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/106 |
| 摩尔线程 | MUSA 5.2.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/107 |
| 摩尔线程 | MUSA 5.2.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/114 |
| 摩尔线程 | MUSA 5.2.0 | megatron_training | https://github.com/flagos-ai/Megatron-LM-FL/pull/127 |

<!-- /status-matrix:verification -->

## 设施落地

> 数据驱动自 `packaging/megatron/status_matrix.*.yaml`（schema 与刷新机制见
> docs/status-matrix.md）。deps_app 落库 = configs.yaml 的 deps_app key 存在
> （该 backend 可构建此 app）；镜像发布 = 该 app 镜像已推送 Harbor。

<!-- status-matrix:facility:megatron_training -->

### megatron_training

> 数据截止：2026-08-26

**App 级设施（全后端共享）**

| 事项 | 状态 |
|---|---|
| Containerfile | ✅ |
| 构建 workflow | ✅ |

**后端级设施**

| 后端 | deps_app 落库 | 启动文档 | 镜像发布 |
|---|---|---|---|
| CUDA 12.8 | ✅ | ✅ | ✅ |
| CUDA 13.3 | ✅ | ✅ | ✅ |
| CANN 8.5.0 | ✅ | ✅ | ⬜ |
| CANN 9.0.0 | ✅ | ✅ | ✅ |
| NEUWARE 4.4.3 | ✅ | ✅ | ✅ |
| NEUWARE 4.7.2 | ✅ | ✅ | ✅ |
| TOPS 1.9.10 | ⬜ | ⬜ | ⬜ |
| TOPS 1.10.6 | ⬜ | ⬜ | ⬜ |
| DTK 26.04 | ✅ | ✅ | ⬜ |
| COREX 4.4.0 | ⬜ | ⬜ | ⬜ |
| XRE 5.37.1 | ⬜ | ⬜ | ⬜ |
| MACA 3.7.2.1 | ⬜ | ⬜ | ⬜ |
| MACA 3.8.1.3 | ✅ | ✅ | ⬜ |
| MUSA 4.3.6 | ⬜ | ⬜ | ⬜ |
| MUSA 5.2.0 | ✅ | ✅ | ✅ |
| SPACEMIT | ⬜ | ⬜ | ⬜ |
| TANGRT 1.2.0 | ⬜ | ⬜ | ⬜ |
| PPU 2.0.0 | ⬜ | ⬜ | ⬜ |
| TSM 260610 | ⬜ | ⬜ | ⬜ |


<!-- /status-matrix:facility:megatron_training -->

<!-- status-matrix:facility:megatron_rl -->

### megatron_rl

> 数据截止：2026-08-24

**App 级设施（全后端共享）**

| 事项 | 状态 |
|---|---|
| Containerfile | ✅ |
| 构建 workflow | ✅ |

**后端级设施**

| 后端 | deps_app 落库 | 启动文档 | 镜像发布 |
|---|---|---|---|
| CUDA 12.8 | ✅ | ✅ | ✅ |
| CUDA 13.3 | ✅ | ✅ | ✅ |
| CANN 8.5.0 | ⬜ | ⬜ | ⬜ |
| CANN 9.0.0 | ⬜ | ⬜ | ⬜ |
| NEUWARE 4.4.3 | ⬜ | ⬜ | ⬜ |
| NEUWARE 4.7.2 | ⬜ | ⬜ | ⬜ |
| TOPS 1.9.10 | ⬜ | ⬜ | ⬜ |
| TOPS 1.10.6 | ⬜ | ⬜ | ⬜ |
| DTK 26.04 | ✅ | ✅ | ⬜ |
| COREX 4.4.0 | ⬜ | ⬜ | ⬜ |
| XRE 5.37.1 | ⬜ | ⬜ | ⬜ |
| MACA 3.7.2.1 | ⬜ | ⬜ | ⬜ |
| MACA 3.8.1.3 | ✅ | ✅ | ⬜ |
| MUSA 4.3.6 | ⬜ | ⬜ | ⬜ |
| MUSA 5.2.0 | ⬜ | ⬜ | ⬜ |
| SPACEMIT | ⬜ | ⬜ | ⬜ |
| TANGRT 1.2.0 | ⬜ | ⬜ | ⬜ |
| PPU 2.0.0 | ⬜ | ⬜ | ⬜ |
| TSM 260610 | ⬜ | ⬜ | ⬜ |


<!-- /status-matrix:facility:megatron_rl -->

## 待合并/待落地修复跟踪（2026-08-21 建）

矩阵 ✅/⬜ 的前提条件拆为三类 pending：上游已提未合并、已实证待提上游
（workaround 在容器侧/配方侧）、决策未决。**状态变更（合并/关闭/新提/定案）
即更新本表对应行**，并联动相应矩阵格与 fact 条目——合并 → 去 workaround →
复验 → 更新格。

### A. 上游已提、未合并

| # | 修复项 | 现状（前提/阻塞） | 上游 | 状态 | 合并后动作 |
|---|---|---|---|---|---|
| 1 | packed_seq 无条件构造 | `--transformer-impl local` 非 TE RL 训练断言炸；unfused 路径亦需此修 | [MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119) / [NVIDIA #6709](https://github.com/NVIDIA/Megatron-LM/pull/6709)（[issue #118](https://github.com/flagos-ai/Megatron-LM-FL/issues/118) / [issue #6708](https://github.com/NVIDIA/Megatron-LM/issues/6708)） | OPEN | RL local 训练解锁 |
| 2 | KV-append 内核设备断言 | 动态批推理首发 KV-append 断言炸（CUDA 白名单） | [MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120) / [NVIDIA #6730](https://github.com/NVIDIA/Megatron-LM/pull/6730)（[issue #6729](https://github.com/NVIDIA/Megatron-LM/issues/6729)） | OPEN | NPU 动态批推理解锁 |
| 3 | flagtree nvidia driver is_active | torch_npu shim 伪造 cuda.is_available → 双后端 is_active 全 True → driver 崩 | [FlagTree #1023](https://github.com/flagos-ai/FlagTree/pull/1023)（[issue #1022](https://github.com/flagos-ai/FlagTree/issues/1022)） | OPEN | ascend flagtree 直接可用 |
| 4 | RL `[rl]` extra 声明 + pin | RL app 镜像不可建（C 机制前置） | [MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114) | OPEN | RL app 镜像解锁 |
| 5 | RL local-impl 5 文件补丁 | metax 容器侧 5 补丁（6 hunk） | [MLF #116](https://github.com/flagos-ai/Megatron-LM-FL/pull/116) | OPEN | 容器补丁取消、落地上游 |
| 6 | wheel 全 scope | #15 任务前置 | [MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) | OPEN | #15 收尾 |
| 7 | jit_fuser 惰性装饰 | hygon flagtree 容器侧 jit.py noop 补丁（§1.4） | [MLF #121](https://github.com/flagos-ai/Megatron-LM-FL/issues/121)→[#122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122) | OPEN | 去容器补丁 |
| 8 | persist_layer_norm 默认 persist=True | ascend post_training 配方需 `--no-persist-layer-norm` | [MLF #123](https://github.com/flagos-ai/Megatron-LM-FL/issues/123)→[#124](https://github.com/flagos-ai/Megatron-LM-FL/pull/124) | OPEN | 去配方参数 |
| 9 | torch-first 导入顺序 | ascend 特有用法前提（flagtree ascend backend discovery 嵌套 import torch，源头 testing.py:27 顶层 import，[#1025](https://github.com/flagos-ai/FlagTree/pull/1025) 已惰性化） | [FlagTree #1024](https://github.com/flagos-ai/FlagTree/issues/1024)→[#1025](https://github.com/flagos-ai/FlagTree/pull/1025) | OPEN | 去用法前提 |

### B. 已实证、待提上游（workaround 当前在容器侧/配方侧）

| # | 修复项 | 现状（workaround） | 上游 | 状态 | 合并后动作 |
|---|---|---|---|---|---|
| 10 | flash_attn 依赖软化 | RL 动态引擎硬依赖 flash_attn（attention.py:943 版本 gate + L677 kernel 断言；L943 已随 [MLF #116](https://github.com/flagos-ai/Megatron-LM-FL/pull/116) DotProductAttention 跳过，L677 待软化） | MLF | 待提 | ascend RL 可走 fallback |
| 11 | mlu 平台抽象缺口 | megatron platform registry（platform_register.py）无 mlu 平台 → cuda 平台经 gpu_migration 桥接选中；PlatformCUDA.device_name()='cuda' vs tensor device.type='mlu' → optimizer.py:773 TypeError | MLF | 已提 [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)（2026-08-22，mlu 平台原生注册，CUDA 前置选中）；已并入集成分支 ci/merge-105-106-107-114 并重建 wheel，无需容器侧补丁，training/post_training/inference 双后端复验全 ✅ | 待 #125 合入 MLF main（合入后仅文档收尾） |

### C. 决策未决 / 工程化

| # | 事项 | 现状 | 归属 | 状态 | 定案后动作 |
|---|---|---|---|---|---|
| 11 | modelopt 入镜像 | 当前 wheel `[training]` extra 声明 `nvidia-modelopt[torch]==0.43.0`（无 `[torch]` extra，pip 仅警告后继续；核心约束 `torch>=2.6`），cambricon 双后端（torch 2.7.1/2.11.0）单步 `megatron-core[training]` 安装实测安全：modelopt 0.43.0 + 完整闭包就位，关键包（torch/torch-mlu/triton/flag_gems）复核未变 | [MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114) | 已实证（0.43.0 安全） | app-image 实建 cambricon 可单步装；**历史 hazard（0.45.0 时代，不再适用）**：旧 extra 曾声明 0.45.0（约束 `torch>=2.8`），4.4.3 下解析出 torch 2.13.0 + CUDA toolkit + triton 3.7.1 → 替换 vendor torch，实测下载阶段 OOM（exit 137）；未来抬 modelopt 版本先核 torch 约束与 `[torch]` extra |
| 12 | ascend RL 路径（npu_fusion_attention 映射 vs Verl） | Ascend ≤950 无 flash_attn，RL 暂停根因；团队倾向用 Verl 承载 ascend 强化学习服务，MLF 侧 RL 方案维持待定 | 用户权衡 | 方案待定 | 定案后更新矩阵 RL 列 |
| 13 | flash-attn nvidia 源码构建 wheel | cuda12.8/13.3 RL E2E 前置 | build-infra | 已完成 | deps_app 已落库 flash_attn（两后端）；psutil 归属待定（公共包，不入 deps_app） |

## 编译器覆盖现状（configs.yaml 2026-08-14）

- **双编译器**（15 backend）：nvidia×2, ascend×2, enflame×2, hygon, iluvatar, kunlunxin, metax×2, mthreads×2, sunrise, tsingmicro
- **仅 triton**（4 backend）：cambricon×2, spacemit, thead

## 已验证/已知事实

各后端 E2E 验证详情已分拆至厂商文档，matrix 仅保留跨后端共享事实与指针：

- **nvidia**（training / post_training×inference / RL / app image，cuda12.8
  与 cuda13.3 双后端）：[[megatron-nvidia-e2e.md]]
- **ascend**（training / post_training×inference / app image / RL 路径三障碍
  上提 + 全链 E2E 暂停）：[[megatron-ascend-e2e.md]]
- **metax**（training / post_training×inference / RL，实证链终止 2026-08-19，
  17 障碍全为本地代码/参数/harness 缺陷）：[[megatron-metax-e2e.md]]
- **cambricon**（training / post_training×inference，NEUWARE 4.4.3+4.7.2
  双后端，triton-only；RL 两端暂缓；首例平台抽象缺口——megatron platform
  registry 无 mlu 平台，已随 [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)
  并入集成分支 wheel 关闭，无需容器侧补丁，见跟踪表 B#11）：
  [[megatron-cambricon-e2e.md]]
- **full-scope wheel 重建（2026-08-22，verify-driver E2E 前置）**：
  `0.17.1+fl.20260822.g56acf36bacd1`（MLF 集成分支
  ci/merge-105-106-107-114 头 `56acf36bacd1`，较旧 4-PR wheel 多
  [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)；PR 全表见
  cambricon 文档）。已上传 flagos-pypi-hosted（cp310 x86_64 / cp311 aarch64 /
  cp312 x86_64），确认含顶层入口 `pretrain_gpt.py` 与 `helpers_cpp` .so——
  verify-driver Step 6（`python -m pretrain_gpt`）所需。cambricon 已用该
  wheel 双后端验证 ✅；nvidia/ascend/metax 文档仍引用旧 wheel，待各自复验。
- **merged wheel 参数接口重构 = 使用方法变更（2026-08-18 定）**：
  hygon 验证用的全范围 wheel 无此问题，merged wheel 引入 config dataclass +
  `ArgumentGroupFactory` 自动生成参数，`--lr`（`SchedulerConfig`）与
  `--eval-interval`（`TrainingConfig`）默认 `None`——不传即崩：`--lr` → 
  `optimizer_param_scheduler.py:148` `float(None)` TypeError；`--eval-interval`
  → `training.py:3672` `train_iters // None` TypeError。**非功能变更，
  是使用方法变更**：训练功能仍在，但喂参接口重构。影响所有用 merged wheel 的后端，
  **hygon 留下的 E2E 参数基线需逐参数重核**（可能有更多参数同样 None 默认）。
  处置（2026-08-18 定，用法侧规避，不回馈上游）：两参数均随 sync
  [NVIDIA #34](https://github.com/NVIDIA/Megatron-LM/pull/34) 来自上游 Core 0.17.0（非 fork 偏离，上游 0.17.0 分支已过时，
  提修复意义不大）；`--eval-interval` 默认 None + 无条件除法 =
  上游已知缺口，`--lr` 属训练必传参数——两者均由复现基线强制传参规避。

- **hygon**（training / post_training×inference / RL，四场景 × 双编译器
  F/T 全 ✅，前提 jit_fuser noop §1.4；编译器机制跨版本不移植，3.3.0 时代
  结论仅参考）：[[megatron-hygon25-e2e.md]]
- **inference 裸 import 阻塞（已由全范围 wheel 关闭）**：
  `megatron/inference/utils.py` 依赖的 `gpt_builders`/`mamba_builders`/
  `model_provider` 是 **repo 根顶层入口文件**（不在 `megatron/` 包内）——
  core-only wheel（0.17.1+flagos）打包时被忽略，安装后
  `import megatron.inference.utils` 即 ImportError。[MLF PR #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107)
  （feat/wheel-full-scope）把顶层入口文件一并打包，hygon 已用该 wheel
  验证推理场景跑通（见下）。
  - **归属**：上游 **core_v0.17.0** 自己的代码（[fork #34](https://github.com/NVIDIA/Megatron-LM/pull/34) 忠实同步），非
    fork 偏离。上游修复时点：0.17.0/0.17.1 = 3 处裸 import；0.18.0/0.18.2
    = 2 处；main = 0（全部收敛进 `megatron/training/models/`）。
  - **状态**：全范围 wheel 从打包侧关闭阻塞（已验证后端见矩阵推理列），
    结构性问题（决策4 关联："顶层文件作入口"模式不支持 wheel 包发布）
    仍然成立，但不阻塞交付。
- **post_training 依赖**：modelopt 是唯一有 vendor 变体的 HARD 依赖
  （configs.yaml 仅 enflame 有 `enflame-modelopt`）；tqdm 纯 PyPI。
  NVIDIA 用 NVIDIA modelopt 可用；其余后端成功率不确定。
- **rl 依赖**：模块级仅 pydantic + typing_extensions（纯 PyPI）；全树
  0 处 triton/torch.compile，复用 training/core 的编译器链。**注意**：
  rl 场景阻塞不在依赖面而在推理引擎——dynamic 引擎硬依赖 flash-attn
  （§5.5；hygon 已由 vendor flash_attn 2.8.3 满足），属场景级缺口，
  非依赖面缺口。

## 编译器层已知问题（来源 vllm 验证，megatron 需实测——不归并）

- kunlunxin P800 XPU：flagtree 0.6.1+xpu3.6 与 vendor triton 3.0.0 均出现 Triton attention-kernel 编译失败（vllm 侧三处）。
- sunrise：flagtree flash-attn decode hang（vllm 侧），`compiler triton` 规避后 E2E 通过。

## 验证顺序建议

1. **training 场景**：先验双编译器后端（编译器链风险已知存在——hygon
   教训），后验单编译器后端。每后端 = runtime 镜像 + wheel 单步安装 +
   pretrain_gpt.py 小规模跑通。
2. **rl 场景**：依赖面干净，验证成本与 training 相当；同镜像按用途补 pydantic/typing_extensions。
3. **post_training 场景**：仅 NVIDIA 先行，其余后端等 modelopt 可用性结论。
4. **inference 场景**：hygon 已用全范围 wheel（[PR #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107)）验证 ✅（static legacy 路径）；其余后端待该 PR 合入后按序验证。
