# Megatron-LM-FL metax E2E 验证记录

验证在 metax（MACA 3.8.1.3，torch 2.10.0）上进行，runtime 镜像
`flagos-runtime-metax:2.1.2`。megatron-core 安装形态为 merged wheel
`0.17.1+fl.20260818.g48b97a13f1bb` 单步安装——该 wheel 来自 MLF 集成分支
ci/merge-105-106-107-114（合入四个 PR）：
[#105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105) /
[#106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106) /
[#107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) /
[#114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)，其中
[#114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114) 声明
`[training]`/`[rl]` extras。验证周期为 2026-08-18 ~ 2026-08-19。
编译器为 flagtree 0.6.1（模块版本 triton 3.6.0）与 vendor triton 3.6.0，
无 jit_fuser noop 补丁前置（flagtree 0.6.1 实测
`--disable-jit-fuser` 直接够用）。

## training（2026-08-18）

**双编译器均 5 iter E2E exit 0**——flagtree 0.6.1（loss 1.084350E+01 →
1.084006E+01）与 vendor triton 3.6.0+metax3.8.1.0（loss 1.084290E+01，
量级与 flagtree 线吻合）。环境要点：huggingface.co 不通 →
NullTokenizer 离线路径。
逐参数原因见 [[hygon.md]] §2 参数基线表（同 wheel、同非
CUDA 平台）。

## post_training × inference（2026-08-18，双编译器全 ✅）

两场景均编译器无关路径，triton/flagtree 各跑一遍全 exit 0——
post_training = DummyModel + `simple_generate`（output shape (1,8)；
modelopt 0.45.0 为临时装入（未入镜像），纳入镜像由
[MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)
的 `[training]` extra 声明承载）；
inference = legacy `StaticInferenceEngine` 3 请求 × 8 tokens。inference
driver 无需外部词表（注入 prompt_tokens + 重写 detokenize，NullTokenizer
配方自洽），metax 容器无 gpt2 夹具也不阻塞。

## RL（双编译器全 ✅；实证链终止 2026-08-19）

flagtree 0.6.1 与 vendor triton 3.6.0 两线均 exit 0，同配方全链通过
（rollout 8 组，GRPO 迭代 1/20，elapsed 30727 ms，0 错误）。真实障碍链（17 个，全 E2E 实证）全为本地代码/参数/harness
缺陷——NullTokenizer pad/bos/eos 缺口、`--return-log-probs` 未注册、
dynamic 批参协调（`max_tokens<max_requests` 断言）、`[rl]` extra
运行时依赖缺失（pyzmq/msgpack/quart/hypercorn/datasets）、flash_attn 2.6.3 的
`flash_decode_and_prefill` 仅 fp16/bf16（`--bf16` 规避）、torch inductor
异步编译 × metax driver `current_device()` fork 崩溃
（`TORCHINDUCTOR_COMPILE_THREADS=1`）、非 streaming drain 断言
（`--rl-partial-rollouts`）、harness eod 去重。**两处环境不合规均实证非阻塞**：
无 vendor TE（`--transformer-impl local` 全程无 TE）+ flash_attn 2.6.3
版本断言不达标但功能支持 block_table 路径（断言是版本号检查非功能检查，
对 vendor 变体不适用）。固化清单（5 补丁 + 4 配方参数）已上提
[MLF #116](https://github.com/flagos-ai/Megatron-LM-FL/pull/116)（OPEN，
见[后续追踪](#后续追踪)）。
运行事实：每次 relaunch 前 kill -9 遗留 pretrain 进程；watcher 只信
log "python exit=" 信号 + 25min 停滞双条件。

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
- [MLF #116](https://github.com/flagos-ai/Megatron-LM-FL/pull/116)
  （RL local-impl 固化：5 补丁 + 4 配方参数）— 合入后容器侧补丁取消，
  重跑 RL，更新矩阵

**通用跟进规则:** 每个上游 PR 合并后 → 重建对应 wheel →
重跑受影响场景 → 更新 [[../megatron-verification-matrix.md]] 跟踪表。
