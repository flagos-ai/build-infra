# Megatron-LM-FL ascend E2E 验证记录

验证在 910B4（aarch64，CANN 9.0.0）上进行，单卡
（ASCEND_VISIBLE_DEVICES=0），runtime 镜像
`flagos-runtime-ascend-cann9.0.0`，Python 3.11，torch 2.10.0+cpu +
torch-npu 2.10.0。验证周期为 2026-08-20。编译器为 flagtree
0.6.1+ascend3.5（`import triton` 报模块版本 3.5.1）与 vendor triton
3.5.0 + triton_ascend 3.2.1（模块版本 3.2.0）。两编译器切换使用
runtime 镜像内置的 `compiler` 命令，下文不重复。

## 前置条件

**wheel:** `0.17.1+fl.20260818.g48b97a13f1bb`，cp311 aarch64，存放于
`flagos-pypi-ascend`（安装时从这里拉取），构建自
flagos-ai/Megatron-LM-FL 的
[ci/merge-105-106-107-114](https://github.com/flagos-ai/Megatron-LM-FL/tree/ci/merge-105-106-107-114)
（commit 48b97a13f）。wheel 制作流程见
[builder/README.md](../../../builder/README.md)（构建环境 = 后端 runtime
镜像，版本号自动带 commit 溯源）。
该分支合入 MLF 的四个 PR：
[MLF #105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105) /
[MLF #106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106) /
[MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) /
[MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)，
其中 [MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)
声明 `[training]`/`[rl]` extras。
本平台装入 `[training]` extra。

**用法前提：torch-first 导入顺序（ascend 特有）**

- **注意事项:** `import triton` 先于 torch、或独立于 torch 导入即崩。
- **原因:** flagtree ascend backend discovery 嵌套 `import torch`，
  触发 torch_npu autoload 失败；源头是 `testing.py:27` 顶层 import。
- **解决:** [FlagTree #1024](https://github.com/flagos-ai/FlagTree/issues/1024)
  （issue）与 [FlagTree #1025](https://github.com/flagos-ai/FlagTree/pull/1025)
  （PR）已把两处 import 惰性化进 `do_bench_npu_profiler` /
  `do_bench_npu_mspti`。
- **现状:** 修复合并前保持 torch-first 顺序；docker exec 经 `bash -c`
  进容器（ASCEND 环境已内置，不加 source）。

## training（双编译器 ✅）

mock data 5 iter，入口 `python -m pretrain_gpt`。
FlagTree 与 Triton 两线均 exit 0：loss 逐 iter 两线逐位一致，
validation test set 两线均 1.084173E+01。

训练参数 = 非 CUDA 平台必传集 + 0.17.1 wheel 必传参数：
--bf16 --no-masked-softmax-fusion --no-gradient-accumulation-fusion
--attention-backend unfused --transformer-impl local --lr 1e-6
--eval-interval 1000。
逐参数原因见 [[hygon.md]] §2 参数基线表
（同 wheel、同非 CUDA 平台）。

## post_training（双编译器 ✅）

DummyModel + `simple_generate`，输出 shape=(1, 8)，两线均 exit 0。
该场景不编译 triton kernel，FlagTree 与 Triton 结果一致。

必须带 `--no-persist-layer-norm`：wheel 参数默认 persist=True，
不带会撞 `torch_norm.py:48` 断言。

modelopt 0.45.0 为临时装入（未入镜像）。
纳入镜像的决策与状态见 [[hygon.md]] §1.3.3。

## inference（双编译器 ✅）

legacy 静态推理引擎，3 请求 × 8 tokens，两线均 exit 0。
该场景不编译 triton kernel。
选 legacy 是因为动态引擎路径依赖 flash-attn，本平台不可用（见 RL 节）。

## megatron_training app image（✅）

镜像 tag:
`flagos-app/megatron_training0.17.1-ascend-cann9.0.0:2.1.2-0.2.1_9.g48b97a13f`。

构建入口: `megatron-app-image.yml`（app=megatron_training，
megatron_version=0.17.1，mlf_version=0.2.1_9.g48b97a13f）。
workflow 内 verify（runtime → app 前后包矩阵 unchanged +
megatron.core import + helpers_cpp bindings）通过后推送。

training 无 vendor 条件包（deps_app.megatron_training0.17.1 = `[]`），
镜像 = runtime + wheel `[training]` extra。

## RL（未实测）

`--transformer-impl local --attention-backend unfused` 下，
GRPO 链（rollout → 参考 logprobs → 训练步）可跑通 exit 0。
unfused 绕开 flash-attn 硬依赖，但非生产路径。
三处代码级障碍已实证并上提（前两处的 MLF 侧已合并，见下）：

1. **packed_seq 无条件构造**（[MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119)
   已合并 `release/0.2`；[NVIDIA #6709](https://github.com/NVIDIA/Megatron-LM/pull/6709) OPEN）:
   `get_logprobs` 与 `train_rl.py` forward_step 在 sequence_packing=False
   时仍无条件构造单序列 thd packed_seq_params（CUDA graph 签名一致性）。
   → local 非融合 DotProductAttention 断言（Packed sequence is not
   supported）。
   修复 = 仅 `rl_training_cuda_graphs` 开启时构造。
2. **KV-append 内核设备断言**（[MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)
   已合并 `release/0.2`；[NVIDIA #6730](https://github.com/NVIDIA/Megatron-LM/pull/6730) OPEN）:
   `triton_append_key_value_cache` 输入校验硬断言 CUDA，
   黑名单改为 `not in ('cpu','meta')`（内核纯 Triton 设备无关；
   910B NPU Triton backend 实跑通过）。
   该 PR 同时平台化 NPU paged attention。
3. **flagtree nvidia driver is_active**（[FlagTree
   #1023](https://github.com/flagos-ai/FlagTree/pull/1023)，OPEN）:
   TORCH_TRANSFER_TO_NPU shim 伪造 `torch.cuda.is_available()`
   （不伪造 `torch.version.cuda`）→ nvidia + ascend 双后端
   is_active 全 True → `triton.runtime.driver._create_driver()` 崩。
   修复 = nvidia is_active 增加 `torch.version.cuda is not None`
   守卫（与上游 triton nvidia driver 同款）。

**2026-09-25 状态（910C 实测）**：`train_rl.py` GRPO 已在两个 910C 后端容器内
跑通全链（rollout → 训练步 2 轮）——hw114（CANN 8.5.0，torch 2.9.0）与
hw115（CANN 9.0.0，torch 2.10.0）均 `TRAIN_RL_EXIT=0`，CANN paged attention
路径实测可用，无需容器侧补丁（与 910B 的 1、2 修复 + #188 平台化直接对齐）。
配方同其余无 flash-attn 后端：`--transformer-impl local --attention-backend
unfused --perform-rl-step --rl-partial-rollouts` + 动态批参数对齐。详见下文
「910C RL E2E」段。910B 全链 E2E 仍待按 `release/0.2` 重建 wheel 后实测（矩阵 ⬜）。

**原暂停原因（2026-08-31 记录，待复核实测）:** 默认 fused 路径动态引擎硬依赖
flash-attn（`attention.py:677`）；Ascend 950 之前的型号（含 910B4）不支持
flash-attn，vendor 包路线关闭。
候选替代 = torch_npu `npu_fusion_attention`（TND varlen）
映射 `flash_decode_and_prefill` 的 prefill/decode 分支
（paged kv 需先还原为连续 TND 布局），方案待定。

## CANN 8.5.0（hw26，2026-08-21）

验证在 910B4-1（aarch64，CANN 8.5.0，driver 25.5.0）上进行，单卡
（ASCEND_VISIBLE_DEVICES=0），runtime 镜像
`flagos-runtime-ascend-cann8.5.0:2.1.2`，Python 3.11，torch 2.9.0+cpu
+ torch-npu 2.9.0。验证周期为 2026-08-21。编译器为 flagtree
0.6.0+ascend3.2（模块版本 triton 3.2.0）与 vendor triton 3.2.0 +
triton_ascend 3.2.0（模块版本 3.2.0）。两编译器切换使用 runtime
镜像内置的 `compiler` 命令，下文不重复。

**wheel:** 同 CANN 9.0.0 段（`0.17.1+fl.20260818.g48b97a13f1bb`，
cp311 aarch64，`flagos-pypi-ascend`），装入 `[training]` extra。
modelopt 0.45.0 随 extra 装入（实测确认），post_training 无需
CANN 9.0.0 的临时补装。

**用法前提：torch-first 导入顺序** 同 CANN 9.0.0（见上节）。

### training（双编译器 ✅）

mock data 5 iter，入口 `python -m pretrain_gpt`。两线均 exit 0，
loss 逐 iter 两线逐位一致，validation test set 均 1.084173E+01——
与 CANN 9.0.0 验证逐位一致（mock 数据确定性复现，跨 CANN 版本成立）。
参数集同 CANN 9.0.0。

### post_training（双编译器 ✅）

DummyModel + `simple_generate`，输出 shape=(1, 8)，两线均 exit 0。
必带 `--no-persist-layer-norm`（同 CANN 9.0.0）。

### inference（双编译器 ✅）

legacy 静态推理引擎，3 请求 × 8 tokens，两线均 exit 0。动态引擎
路径依赖 flash-attn，本平台不可用（见 RL 节）。

### RL（910B 路径未实测 / 910C 已实测）

同 CANN 9.0.0：910B4 无 flash-attn，本条路径上的三处代码级障碍
（[MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119) /
[MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120) /
[FlagTree #1023](https://github.com/flagos-ai/FlagTree/pull/1023)）
中前两处已随 `release/0.2` 合入（2026-09-22），仅 FlagTree #1023 仍未合；
910B 全链 E2E 尚未跑过（矩阵 ⬜），细节见 CANN 9.0.0 段 RL 节。
**注**：NPU 平台自带 paged attention，[MLF #188](https://github.com/flagos-ai/Megatron-LM-FL/pull/188)
（paged 分派按能力查询）不改变 NPU 行为——无 flash-attn 在这里从来不是分派侧的阻塞。
910C 两个后端的 RL 全链已实测跑通（见 CANN 9.0.0 段 RL 节末的「910C RL E2E」）。

## 910C RL E2E（2026-09-25）

两个 910C 后端容器内各自跑通 `train_rl.py` GRPO 全链（rollout → 训练步
2 轮），`TRAIN_RL_EXIT=0`：

- **hw115**（CANN 9.0.0，`flagos-runtime-ascend-cann9.0.0-910c:2.2.0`，
  torch 2.10.0 + torch-npu 2.10.0，容器 `rl10-e2e`，装
  `megatron-core[rl]==0.17.1+fl.0.2.3`）；另需 `einops`（`attention.py`
  `rearrange` 的 lazy import 落到 None）——经 runner 代理装。
- **hw114**（CANN 8.5.0，`flagos-runtime-ascend-cann8.5.0-910c:2.2.0`，
  torch 2.9.0 + torch-npu 2.9.0，容器 `rl10-e2e-hw114`，同 wheel；
  einops 同样经代理装）。

与 910B 的修复对齐，无需容器侧补丁（wheel 已含 #119/#120/#188 平台化）。
两容器各一处容器侧小改：einops 需装入（lazy `rearrange`，见上）；
`megatron/inference/utils.py` 的 `--return-log-probs` 与
`megatron/training/arguments.py` 的 inference 段注册冲突（同一 flag 两侧
`add_argument`），需将 utils.py 侧改名为 `--inference-return-log-probs`
（与 910B 早期配方一致）。GRPO 链实跑: rollouts 全链（64 条 dummy prompt
× group 4 → rollout）→ 训练步 2 轮，两容器 `[after training is done]` 后
`TRAIN_RL_EXIT=0`。
配方要点（同其余无 flash-attn 后端）：
`--transformer-impl local --attention-backend unfused --perform-rl-step
--rl-partial-rollouts`，`grpo-prompts-per-step × grpo-group-size ×
grpo-iterations` 需被 `global-batch-size` 整除（本轮
prompts=16×group=4×iter=2=64 ÷ gbs=16 = 4），动态批 `max-requests/max-tokens`
须如实给出（配套图；框架未代填），token 用 `NullTokenizer`（prompt 逐个
空格分隔的 int）。RL 场景在 app 镜像矩阵上按后端标 ✅。

## 后续追踪

**已合并、待按新 wheel 复验（MLF 侧 2026-09-22 全部合入 `release/0.2`）:**

- [MLF #105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105)
  （core 独立 import 修复：`megatron.training` 缺席时
  `is_built_on_zero_rank` import 修复）
- [MLF #106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106)
  （psutil 运行时依赖声明）
- [MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107)
  （full-scope 打包：wheel 覆盖四场景 + 顶层入口模块）
- [MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)
  （声明 `[training]`/`[rl]` extras 与 pin）
- [MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119)
  （packed_seq gate）— RL unfused 前置
- [MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)
  （KV-append 断言 + NPU paged attention 平台化）
- [FlagTree #1024](https://github.com/flagos-ai/FlagTree/issues/1024) /
  [FlagTree #1025](https://github.com/flagos-ai/FlagTree/pull/1025)
  （testing.py 惰性化）— **已合并（2026-09-04）**；重建 flagtree wheel 后解除
  「torch-first 导入顺序」用法前提

**未合并（等上游 merge）:**

- [FlagTree #1023](https://github.com/flagos-ai/FlagTree/pull/1023)
  （nvidia driver is_active 守卫）— 重建 flagtree wheel，重跑 RL，更新矩阵

**待决（需权衡）:**

- flash-attn 替代方案：npu_fusion_attention 映射
  `flash_decode_and_prefill`（paged kv 需还原连续 TND 布局）
  ——决定后 RL 全链 E2E 可继续。

**通用跟进规则:** 每个上游 PR 合并后 → 重建对应 wheel →
重跑受影响场景 → 更新 [[../megatron-verification-matrix.md]] 跟踪表。
