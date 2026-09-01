# Megatron-LM-FL 0.17.1 验证报告

## 背景

megatron app 镜像（`megatron_training` / `megatron_rl`）= runtime 镜像 +
megatron-core wheel 单步安装（**不 `--no-deps`**）。wheel 从
[Megatron-LM-FL](https://github.com/flagos-ai/Megatron-LM-FL) fork 源码构建
（`packaging/megatron/builder/`），版本号 `0.17.1+fl.<date>.g<sha>`——本地段
= fork commit 溯源（日期 + 精确 commit），PEP 440 忽略 local label，
`==0.17.1` 匹配不受影响。

与 vllm/sglang 的 repack 模型不同，megatron 是 **fork 源码 wheel 模型**：
保留 `torch>=2.6.0` Requires-Dist，由 runtime 的 vendor torch 满足，pip
解析零下载、单步安装惰性。wheel 按 extra 选择器携带场景依赖：

- `[training]`：pretrain_gpt 训练 + post_training（modelopt）场景
- `[rl]`：GRPO 强化学习场景

wheel 含编译扩展 `megatron.core.datasets.helpers_cpp`（pybind11），
CPython-ABI 特定——cp310 / cp311 / cp312 三版本全部构建并上传（runtime
矩阵三种 Python 都在用）。构建环境 = 后端 runtime 镜像本身，ABI 契约按
构造匹配（见 [report-builder.md](report-builder.md)）。

## 后端索引

| 后端 | 文档 | 状态 |
|---|---|---|
| nvidia（CUDA 12.8 / 13.3） | [backends/nvidia.md](backends/nvidia.md) | 四场景 × 双编译器全 ✅；training/rl app 镜像已 push |
| hygon（DTK 26.04） | [backends/hygon.md](backends/hygon.md) | 四场景 × 双编译器全 ✅（flagtree 需 jit_fuser noop） |
| metax（MACA 3.8.1.3） | [backends/metax.md](backends/metax.md) | 四场景 × 双编译器全 ✅；17 障碍全闭环 |
| ascend（CANN 8.5.0 / 9.0.0） | [backends/ascend.md](backends/ascend.md) | training / post_training / inference ✅；RL 暂停（无 flash-attn） |
| cambricon（NEUWARE 4.4.3 / 4.7.2） | [backends/cambricon.md](backends/cambricon.md) | 三场景 ✅（triton-only）；RL 暂缓 |
| enflame（TOPS 1.9.10 / 1.10.6） | [backends/enflame.md](backends/enflame.md) | training 双编译器 ✅（flagtree 需 jit_fuser noop；1.10.6 另需 ECCL fp64 patch） |
| iluvatar（CoreX 4.4.0 / 4.5.0） | [backends/iluvatar.md](backends/iluvatar.md) | training 双编译器 ✅，零 workaround |

完整状态见 [../megatron-verification-matrix.md](../megatron-verification-matrix.md)。

## 版本级结论

- **阶段一（验证面）**：四场景（training / post_training / inference / RL）×
  双编译器（flagtree / triton）在 nvidia、hygon、metax 全 ✅；ascend 前三
  场景 ✅、RL 暂停（动态引擎硬依赖 flash-attn，910B4 无）。编译器验证面
  不归并：每后端 × 双编译器分别验证。
- **阶段二（固化）**：deps_app 机制（[build-infra PR #424](https://github.com/flagos-ai/build-infra/pull/424)）、Containerfile 拆分
  （[build-infra PR #427](https://github.com/flagos-ai/build-infra/pull/427)）、apex 纳入 hygon runtime（[build-infra PR #422](https://github.com/flagos-ai/build-infra/pull/422)）、app 参数化 workflow
  （[build-infra PR #425](https://github.com/flagos-ai/build-infra/pull/425)）、TORCHINDUCTOR_COMPILE_THREADS 固化（[build-infra PR #443](https://github.com/flagos-ai/build-infra/pull/443)）全部合并。
- **app 镜像**：megatron_training / megatron_rl 在 nvidia 双后端构建 + 验证 +
  push 全 ✅；training 无 vendor 条件包（deps_app = `[]`），rl 仅 hygon 有
  vendor TE（transformer_engine）。

## 遗留

- **MLF PR 全 OPEN**：[MLF #105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105)（core 独立 import）、[MLF #106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106)（psutil 声明）、[MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107)
  （wheel 全 scope）、[MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)（`[rl]` extra）、[MLF #116](https://github.com/flagos-ai/Megatron-LM-FL/pull/116)（RL local-impl 5 文件补丁）、
  [MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119)（packed_seq gate）、[MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)（KV-append 断言 + NPU paged attention）、
  [MLF #122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122)（jit_fuser 惰性装饰）、[MLF #124](https://github.com/flagos-ai/Megatron-LM-FL/pull/124)（persist_layer_norm 默认）、[MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)（mlu
  平台注册）——每个合并后重建 wheel、重跑受影响场景、更新矩阵（跟踪表见
  verification-matrix「待合并/待落地修复跟踪」）。
- **cambricon 需复验**：runtime 5.3.3 之后 +39k kernel rewrite，neuware
  4.7.2:2.1.2 的 E2E 结果不再背书新产物（见 [backends/cambricon.md](backends/cambricon.md)）。
- **决策未决**：modelopt 入镜像的版本约束演进（抬版本前先核 torch 约束）。
- **megatron_rl 降级（2026-08-31 定案）**：RL 框架转向 verl，megatron_rl 全线暂停（矩阵 RL 列 ⏸），验证随 verl 线推进。
