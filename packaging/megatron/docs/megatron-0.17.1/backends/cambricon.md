# Megatron-LM-FL cambricon E2E 验证记录

验证在寒武纪两个后端上进行，均为 triton-only（矩阵 F 列 = —）：

| 后端 | runtime 镜像 | Python | torch | torch-mlu | triton（/opt/triton） | flag_gems |
|---|---|---|---|---|---|---|
| NEUWARE 4.4.3 | `flagos-runtime-cambricon-neuware4.4.3:2.1.2` | 3.10 | 2.7.1+cpu | 1.29.2+torch2.7.1 | 3.2.0+mlu1.7.2 | 5.3.4 |
| NEUWARE 4.7.2 | `flagos-runtime-cambricon-neuware4.7.2:2.1.2` | 3.12 | 2.11.0+cpu | 1.33.1+torch2.11.0 | 3.4.0+mlu2.1.1 | 5.3.4 |

megatron-core 安装形态为 merged wheel
`0.17.1+fl.20260822.g56acf36bacd1` 单步安装——该 wheel 来自 MLF 集成分支
ci/merge-105-106-107-114（合入五个 PR）：
[MLF #105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105) /
[MLF #106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106) /
[MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) /
[MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114) /
[MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)（分支头
`56acf36ba` = merge origin/pr-125）。wheel 经 megatron-wheel.yml 为两后端
各构建一次（cp310/cp312），上传至 flagos-pypi-cambricon。验证周期
2026-08-22（含 [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)
并入集成分支后的复验），节点为 MLU590-M9DE（8 卡）。

## training（2026-08-22，双后端全 ✅）

5-iter pretrain_gpt E2E exit 0（4.4.3 MASTER_PORT=29500 / 4.7.2 29501）。
复验（aggregate wheel）loss 与此前验证逐字节一致。

- 4.4.3：iteration 1/5 lm loss **5.989294E+00**（9697.1 ms，首 iter Triton
  compile），grad norm 2.730；validation-set 5.972318E+00 | PPL 3.924143E+02；
  test-set 5.973097E+00 | PPL 3.927200E+02
- 4.7.2：iteration 1/5 lm loss **5.989294E+00**（14698.9 ms），grad norm 2.730；
  validation-set 5.972326E+00 | PPL 3.924175E+02；test-set 5.973097E+00 |
  PPL 3.927200E+02

**跨后端一致性**：iteration-1 loss 与 test-set validation loss 与 4.4.3
**逐字节相同**（5.989294E+00 / 5.973097E+00）；validation-set 仅第 5 位小数不同（5.972318 vs 5.972326）——eval RNG seeding 跨 torch 版本差异，记录为
observed 非错误。loss 量级 ~5.97 与 metax 基线 ~1.08E+01 不同——不同
torch/平台，同样记录为 observed。

## 平台抽象缺口（cambricon 首例，跟踪表 B#11）

**megatron platform registry（platform_register.py）无 mlu 平台**（仅
cpu/cuda/musa/txda/npu/enflame/kunlunxin）→ cuda 平台经 gpu_migration 桥接
选中。引发三个断点：

1. `torch.cuda.is_available()` False（MLU 非 CUDA）→ megatron
   `assert torch.cuda.is_available()` 炸。
2. **RNG tracker 设备初始化缺口**：设备初始化前
   `torch.cuda.default_generators` 为空 `[]` → random.py:167
   `default_generators[idx]` IndexError/裸 Generator TypeError。
3. **device_name 错配**：`PlatformCUDA.device_name()='cuda'` vs 张量
   `device.type='mlu'` → optimizer.py:773
   `TypeError: Wrapped parameters must be one of accelerator ... Received
   torch.mlu.BFloat16Tensor`。

上游修复已提 [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)
（2026-08-22）：PlatformMLU 原生注册，继承 PlatformCUDA（gpu_migration
桥接），`is_available()` 强制设备初始化，MLU 注册/选中均在 CUDA 之前；
含 4 个单测。**[MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)
已并入集成分支并重建 wheel（`0.17.1+fl.20260822.g56acf36bacd1`），
三场景复验全 ✅**（training / post_training / inference 均打印
`mlu Selected`，见下文各节）。待 [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)
合入 MLF main 即完全落地。

其余配方参数缺口（merged wheel config dataclass，与 metax/hygon 同源）：
`--max-position-embeddings`（arguments.py:1131 默认 None 断言）、
`MASTER_ADDR/MASTER_PORT`（env:// rendezvous）。

## post_training（2026-08-22，双后端全 ✅）

post_training = DummyModel + `simple_generate`（surface-imports 全部
megatron.post_training.*，checkpointing.py:7 模块级 `import modelopt.torch`）
exit 0，`output shape = (1, 8)`，0 Traceback。编译器无关路径（sdpa，无
triton kernel）。

**modelopt 依赖面（跟踪表 C#11 现状更新）**：当前 wheel 的 `[training]` extra
声明 `nvidia-modelopt[torch]==0.43.0`——0.43.0 无 `[torch]` extra（pip 仅
警告后继续），核心约束 `torch>=2.6`，双后端（torch 2.7.1+cpu / 2.11.0+cpu）
均满足。单步 `pip install "megatron-core[training]==0.17.1+fl.20260822.g56acf36bacd1"`
（vendor index 主、aliyun 备）即装齐 modelopt 0.43.0 + 完整闭包，关键包
（torch/torch-mlu/triton/flag_gems）复核未变，`import modelopt.torch` OK。

- **规则（用户定）**：关键包（torch/torch-mlu/triton/flag_gems）一律不升级。
- **历史 hazard（0.45.0 时代，当前 wheel 不再适用）**：旧 wheel 的
  `[training]` extra 曾声明 `nvidia-modelopt[torch]==0.45.0`（约束
  `torch>=2.8`），4.4.3（torch 2.7.1+cpu）下全依赖装会解析出 torch 2.13.0 +
  CUDA toolkit 并替换 vendor torch——实测下载阶段 OOM 被杀（exit 137）。
  0.43.0 pin 后该路径不存在；若未来 extra 再抬 modelopt 版本，先核其 torch
  约束与 `[torch]` extra 有无。

## inference（2026-08-22，双后端全 ✅）

inference = legacy `StaticInferenceEngine` 3 请求 × 8 tokens（prompt_tokens
注入 + detokenize 重写，NullTokenizer 配方自洽）exit 0，0 Traceback。
4.7.2 日志有一条 `torch._inductor.exc.InductorError: No module named
'triton'`（torch_mlu 1.33.1 inductor triton_fusion 插件顶层 import 失败，
捕获后非致命——推理走 sdpa，不触碰 inductor）记录为 observed。

静态 legacy 路径不需要动态批（KV-append 内核设备断言，跟踪表 #2
[MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)），故推理
⛔→✅；**动态批推理仍被 [MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)
阻塞**（矩阵 ⛔ 的原始语义）。

## RL（暂缓）

按验证决策，cambricon 两后端 RL **两端都暂缓**（矩阵 RL 列维持 ⬜）；
待其他后端 RL 路径定案后统一处理。

## 后续追踪

- 平台抽象缺口（#11）已随 [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)
  并入集成分支并重建 wheel（`0.17.1+fl.20260822.g56acf36bacd1`）：复验
  training / post_training / inference 双后端全 ✅（矩阵 B#11 已同步）。
  [MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125)
  上游保持 OPEN，按决策不等待其 merge；合入 main 后仅剩文档表述收尾。
- modelopt 已随当前 wheel 的 `[training]` extra（0.43.0）实测安全：单步安装、
  关键包未动（详见上文 modelopt 依赖面）——0.45.0 时代 hazard 不再适用，
  未来抬 modelopt 版本需先核 torch 约束。
