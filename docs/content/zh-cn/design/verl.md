---
title: verl
weight: 80
---

<!--
 Copyright 2026 FlagOS Contributors

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 -->


verl app 镜像 = runtime 镜像 + 从 verl-FL fork 构建的 wheel 的**单步
`pip install`**。verl 是纯 Python，wheel 为 `py3-none-any`——**一个 wheel 通吃
17 个后端**，无 per-ABI 拆分。训练走 megatron-core，rollout 走 vllm +
vllm-plugin-fl；平台由 `VERL_PLATFORM` 选择。

## 一个 wheel，一套矩阵

verl 是 **fork-source** 包（同 megatron，异于 vllm/sglang 的 repack）。其
`numpy<2.0.0` 约束由 runtime 的 stack-wide `numpy==1.26.4` pin 天然满足，
安装无需 `--no-deps`、无需依赖手术。runtime 没有、verl 需要的依赖
（ray/datasets/peft/tensordict/wandb/…）落在 `deps_app.verl0.7.0`。

## 两个已在栈内的引擎

- **megatron-core，基础版** —— verl 只 import `megatron.core.*`，从不碰
  `megatron.rl`。`[rl]` 附加会反向降级 verl 自己锁定的依赖，故不装。
- **rollout vllm，分支路线** —— verl 0.7.0 自带 vllm 线（0.11/0.12）与
  vllm-plugin-FL（≥0.13）交集为空，故把 fork 的版本门补丁到 0.20.2 线，
  rollout 复用 `vllm==0.20.2+flagos` + 现有 plugin wheel。该补丁是否进入
  verl-FL 主线由 verl-FL 团队评估。

## 可选层

- **TE-FL** —— `TE_FL_SKIP_CUDA=1` 使其成为 `py3-none-any` wheel；独立发布，
  是优化层而非硬要求（verl 惰性 import）。
- **FlagCX** —— 无硬依赖，默认回退 vendor 原生 nccl/hccl/mccl。启用时
  `USE_FLAGCX` 与 `FLAGCX_PATH` 必须成对设置。

## 完整理由

设计记录就在代码旁：

- [packaging/verl/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/verl/DESIGN.md) —— 决策，面向维护者。
- [packaging/verl/docs/verl-app-image-plan.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/verl/docs/verl-app-image-plan.md) —— 实施计划。
- [packaging/verl/docs/verl-hygon-e2e.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/verl/docs/verl-hygon-e2e.md) —— 首个后端 E2E 报告。
