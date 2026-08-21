# Megatron-LM-FL ascend E2E 验证记录

**验证环境:** 910B4（aarch64，CANN 9.0.0），runtime 镜像
`flagos-runtime-ascend-cann9.0.0`，python 3.11、torch 2.10.0+cpu +
torch-npu 2.10.0、ASCEND_VISIBLE_DEVICES=0。
**安装形态:** merged wheel `0.17.1+fl.20260818.g48b97a13f1bb` 单步安装
（[training] extra 随 wheel 装入；wheel 已上传 flagos-pypi-ascend，
cp311 aarch64）。
**验证周期:** 2026-08-20。

编译器版本（2026-08-20 实测）：F 列 = flagtree 0.6.1+ascend3.5（默认
/opt/flagtree，`import triton` 报模块版本 3.5.1）；T 列 = vendor triton
3.5.0 + triton_ascend 3.2.1（`compiler triton` → /opt/triton，`import
triton` 报模块版本 3.2.0）。**用法侧要求（ascend 特有）**：torch-first
导入顺序（`import triton` 先于或独立于 torch 崩：flagtree ascend backend
discovery 嵌套 import torch → torch_npu autoload 失败，源头
testing.py:27 顶层 import，FlagTree #1024→#1025 已惰性化）；docker exec
须经 bash -c 进容器（ASCEND 环境已内置，不加 source）。

## training（2026-08-20，双编译器全 ✅）

mock data 5 iter E2E **双编译器均 exit 0**——F 列 flagtree 0.6.1+ascend3.5
（默认 /opt/flagtree，模块版本 3.5.1）与 T 列 vendor triton 3.5.0 +
triton_ascend 3.2.1（`compiler triton` → /opt/triton，模块版本 3.2.0）；
**逐 iter loss 两线完全一致**：1.084308/1.084362/1.084429/1.083861/
1.083677，validation test set 两线均 1.084173E+01（mock 数据确定性复现，
与 hygon/metax 量级一致）。无 jit 补丁前置，`--disable-jit-fuser`
直接够用。

## post_training × inference（2026-08-20，双编译器全 ✅）

两场景均编译器无关路径，同 nvidia/metax 配方——post_training = DummyModel +
`simple_generate`（output shape (1,8)，modelopt 0.45.0 ad-hoc 装入，
aliyun 带依赖解析，含 requests/huggingface_hub 传递依赖链，未入镜像，同
hygon 报告 §1.3.3 modelopt 决策未决）；inference = legacy
`StaticInferenceEngine` 3 请求 × 8 tokens。F/T 双线均 exit 0。
**唯一障碍：post_training 首跑漏传 `--no-persist-layer-norm`** →
`torch_norm.py:48` 断言（merged wheel 参数默认 persist=True，同 nvidia
cuda12.8 inference 教训——训练配方参数集需逐参数随行）；补传后
F/T 双线全过。

## megatron-training app image（2026-08-20，✅）

`flagos-app/megatron_training0.17.1-ascend-cann9.0.0:2.1.2-0.2.1_9.g48b97a13f`
已构建并推送（tag 命名与 nvidia 一致：应用版本 0.17.1 + fork 版本
0.2.1_9.g48b97a13f）。app=megatron-training、megatron_version=0.17.1、
mlf_version=0.2.1_9.g48b97a13f，workflow 内 verify（--app-image 模式：
BEFORE(runtime) vs AFTER(app) 矩阵逐包 unchanged + megatron.core import +
helpers_cpp bindings OK）通过后 push。training 无 vendor 条件包
（deps_app.megatron-training = `[]`）——镜像 = runtime + wheel
`[training]` extra 单步安装（wheel 已上传 flagos-pypi-ascend，
cp311 aarch64）。

## RL 路径（2026-08-20，三处代码级障碍实证 + 修复上提；全链 E2E 暂停）

在 910B（CANN 9.0.0，torch_npu + TORCH_TRANSFER_TO_NPU）上以
`--transformer-impl local --attention-backend unfused` 跑通 GRPO 训练链
（rollout → 参考 logprobs → 训练步，exit 0；unfused 路径绕开 flash_attn
硬依赖），暴露三处代码级问题，均已修复并上提：

1. **packed_seq 无条件构造（MLF issue #118 + PR #119，NVIDIA #6708 +
   #6709，均 OPEN）**：`get_logprobs` 与 `train_rl.py` forward_step 在
   sequence_packing=False 时无条件构造单序列 thd packed_seq_params（CUDA
   graph 签名一致性）→ `--transformer-impl local` 非融合
   DotProductAttention 断言（Packed sequence is not supported）。修复 =
   仅 `rl_training_cuda_graphs` 开启时构造（单序列 thd == dense），
   关闭时保持 None 走 unfused 路径。非 TE RL 训练前置，已实证。
2. **KV-append 内核设备断言（MLF PR #120，NVIDIA #6729 + #6730，均
   OPEN）**：`triton_append_key_value_cache` 输入校验硬断言 CUDA → 黑名单
   `not in ('cpu','meta')`（内核纯 Triton 设备无关；910B NPU Triton
   backend 实跑通过——动态批推理 KV-append 路径前置）。PR #120 主体的
   NPU paged attention 平台化（paged-attention capability hooks + NPU
   dispatch + dist.gather_object 兼容）同属该路径前置。
3. **flagtree nvidia driver is_active（FlagTree issue #1022 + PR #1023，
   均 OPEN）**：TORCH_TRANSFER_TO_NPU shim 伪造 `torch.cuda.is_available()`
   （不伪造 `torch.version.cuda`）→ nvidia + ascend 双后端 is_active 全
   True → `triton.runtime.driver._create_driver()` 崩。修复 = nvidia
   is_active 增加 `torch.version.cuda is not None`（与上游 triton nvidia
   driver 同款守卫；修复后 amd=False, ascend=True, nvidia=False →
   NPUDriver）。

**RL 全链 E2E 暂停（矩阵 ⬜）**：默认 fused 路径动态引擎硬依赖 flash_attn
（attention.py:677）——用户已查证（2026-08-20）：Ascend 950 之前的型号
（含 910B4）不支持 flash_attn，vendor 包路线关闭；候选替代 =
torch_npu `npu_fusion_attention`（TND varlen）映射
`flash_decode_and_prefill` 的 prefill 分支（`flash_attn_varlen_func`）
与 decode 分支（`flash_attn_with_kvcache`），paged kv（block_table）
需先还原为连续 TND 布局——**方案待用户权衡**。
unfused 可跑通但非生产路径。
