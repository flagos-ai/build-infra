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
[builder/README.md](../../builder/README.md)（构建环境 = 后端 runtime
镜像，版本号自动带 commit 溯源）。
该分支合入 MLF 的四个 PR：
[#105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105) /
[#106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106) /
[#107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) /
[#114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)，
其中 [#114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)
声明 `[training]`/`[rl]` extras。
本平台装入 `[training]` extra。

**用法前提：torch-first 导入顺序（ascend 特有）**

- **注意事项:** `import triton` 先于 torch、或独立于 torch 导入即崩。
- **原因:** flagtree ascend backend discovery 嵌套 `import torch`，
  触发 torch_npu autoload 失败；源头是 `testing.py:27` 顶层 import。
- **解决:** [FlagTree #1024](https://github.com/flagos-ai/FlagTree/issues/1024)
  （issue）与 [#1025](https://github.com/flagos-ai/FlagTree/pull/1025)
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
逐参数原因见 [[megatron-hygon25-e2e.md]] §2 参数基线表
（同 wheel、同非 CUDA 平台）。

## post_training（双编译器 ✅）

DummyModel + `simple_generate`，输出 shape=(1, 8)，两线均 exit 0。
该场景不编译 triton kernel，FlagTree 与 Triton 结果一致。

必须带 `--no-persist-layer-norm`：wheel 参数默认 persist=True，
不带会撞 `torch_norm.py:48` 断言。

modelopt 0.45.0 为临时装入（未入镜像）。
纳入镜像的决策与状态见 [[megatron-hygon25-e2e.md]] §1.3.3。

## inference（双编译器 ✅）

legacy 静态推理引擎，3 请求 × 8 tokens，两线均 exit 0。
该场景不编译 triton kernel。
选 legacy 是因为动态引擎路径依赖 flash-attn，本平台不可用（见 RL 节）。

## megatron-training app image（✅）

镜像 tag:
`flagos-app/megatron_training0.17.1-ascend-cann9.0.0:2.1.2-0.2.1_9.g48b97a13f`。

构建入口: `megatron-app-image.yml`（app=megatron-training，
megatron_version=0.17.1，mlf_version=0.2.1_9.g48b97a13f）。
workflow 内 verify（runtime → app 前后包矩阵 unchanged +
megatron.core import + helpers_cpp bindings）通过后推送。

training 无 vendor 条件包（deps_app.megatron-training = `[]`），
镜像 = runtime + wheel `[training]` extra。

## RL（全链 E2E 暂停）

`--transformer-impl local --attention-backend unfused` 下，
GRPO 链（rollout → 参考 logprobs → 训练步）可跑通 exit 0。
unfused 绕开 flash-attn 硬依赖，但非生产路径。
三处代码级障碍已实证并上提：

1. **packed_seq 无条件构造**（[MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119)
   / [NVIDIA #6709](https://github.com/NVIDIA/Megatron-LM/pull/6709)，OPEN）:
   `get_logprobs` 与 `train_rl.py` forward_step 在 sequence_packing=False
   时仍无条件构造单序列 thd packed_seq_params（CUDA graph 签名一致性）。
   → local 非融合 DotProductAttention 断言（Packed sequence is not
   supported）。
   修复 = 仅 `rl_training_cuda_graphs` 开启时构造。
2. **KV-append 内核设备断言**（[MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)
   / [NVIDIA #6730](https://github.com/NVIDIA/Megatron-LM/pull/6730)，OPEN）:
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

**暂停原因:** 默认 fused 路径动态引擎硬依赖 flash-attn
（`attention.py:677`）；Ascend 950 之前的型号（含 910B4）不支持
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

### RL（全链 E2E 暂停）

同 CANN 9.0.0：910B4 无 flash-attn，三处代码级障碍
（[MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119) /
[#120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120) /
[FlagTree #1023](https://github.com/flagos-ai/FlagTree/pull/1023)）
未合并，路径未验证，细节见 CANN 9.0.0 段 RL 节。

## 后续追踪

**待合并（等上游 merge）:**

- [MLF #105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105)
  （core 独立 import 修复：`megatron.training` 缺席时
  `is_built_on_zero_rank` import 修复）— MLF main 未合；
  合入后重建 wheel，重跑受影响场景，更新矩阵
- [MLF #106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106)
  （psutil 运行时依赖声明）— 同上
- [MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107)
  （full-scope 打包：wheel 覆盖四场景 + 顶层入口模块）— 同上
- [MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)
  （声明 `[training]`/`[rl]` extras，含 `nvidia-modelopt==0.45.0` 锁版）—
  **当前只合入集成分支 ci/merge-105-106-107-114，MLF main 未合**；
  合入前 main 构建的 wheel 不带 modelopt → 合入后重建 wheel，更新矩阵
- [MLF #119](https://github.com/flagos-ai/Megatron-LM-FL/pull/119)
  （packed_seq gate）— 合入后重建 wheel，重跑 RL unfused 前置，更新矩阵
- [MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)
  （KV-append 断言 + NPU paged attention 平台化）— 同上
- [FlagTree #1023](https://github.com/flagos-ai/FlagTree/pull/1023)
  （nvidia driver is_active 守卫）— 重建 flagtree wheel，
  重跑 RL，更新矩阵
- [FlagTree #1024](https://github.com/flagos-ai/FlagTree/issues/1024) /
  [#1025](https://github.com/flagos-ai/FlagTree/pull/1025)
  （testing.py 惰性化）— 重建 flagtree wheel 后解除「torch-first
  导入顺序」用法前提

**待决（需权衡）:**

- flash-attn 替代方案：npu_fusion_attention 映射
  `flash_decode_and_prefill`（paged kv 需还原连续 TND 布局）
  ——决定后 RL 全链 E2E 可继续。

**通用跟进规则:** 每个上游 PR 合并后 → 重建对应 wheel →
重跑受影响场景 → 更新 [[megatron-verification-matrix.md]] 跟踪表。
