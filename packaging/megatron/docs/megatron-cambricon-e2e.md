# Megatron-LM-FL cambricon E2E 验证记录

验证在寒武纪两个后端上进行，均为 triton-only（矩阵 F 列 = —）：

| 后端 | runtime 镜像 | Python | torch | torch-mlu | triton（/opt/triton） | flag_gems |
|---|---|---|---|---|---|---|
| NEUWARE 4.4.3 | `flagos-runtime-cambricon-neuware4.4.3:2.1.2` | 3.10 | 2.7.1+cpu | 1.29.2+torch2.7.1 | 3.2.0+mlu1.7.2 | 5.3.4 |
| NEUWARE 4.7.2 | `flagos-runtime-cambricon-neuware4.7.2:2.1.2` | 3.12 | 2.11.0+cpu | 1.33.1+torch2.11.0 | 3.4.0+mlu2.1.1 | 5.3.4 |

megatron-core 安装形态为 merged wheel
`0.17.1+fl.20260818.g48b97a13f1bb` 单步安装——该 wheel 来自 MLF 集成分支
ci/merge-105-106-107-114（合入四个 PR）：
[#105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105) /
[#106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106) /
[#107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) /
[#114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114)。wheel 经
megatron-wheel.yml 为两后端各构建一次（cp310/cp312），上传至
flagos-pypi-cambricon。验证周期 2026-08-22，节点为 MLU590-M9DE（8 卡）。

## training（2026-08-22，双后端全 ✅）

5-iter pretrain_gpt E2E exit 0（4.4.3 MASTER_PORT=29500 / 4.7.2 29501）。

- 4.4.3：iteration 1/5 lm loss **5.989294E+00**（11984.9 ms，首 iter Triton
  compile），grad norm 2.730；validation-set 5.972318E+00 | PPL 3.924143E+02；
  test-set 5.973097E+00 | PPL 3.927200E+02
- 4.7.2：iteration 1/5 lm loss **5.989294E+00**（14371.8 ms），grad norm 2.730；
  validation-set 5.972326E+00 | PPL 3.924175E+02；test-set 5.973097E+00 |
  PPL 3.927200E+02

**跨后端一致性**：iteration-1 loss 与 test-set validation loss 与 4.4.3
**逐字节相同**（5.989294E+00 / 5.973097E+00）；validation-set 仅第 5 位小数不同（5.972318 vs 5.972326）——eval RNG seeding 跨 torch 版本差异，记录为
observed 非错误。loss 量级 ~5.97 与 metax 基线 ~1.08E+01 不同——不同
torch/平台，同样记录为 observed。

## 平台抽象缺口（cambricon 首例，跟踪表 #11）

**megatron platform registry（platform_register.py）无 mlu 平台**（仅
cpu/cuda/musa/txda/npu/enflame/kunlunxin）→ cuda 平台经 gpu_migration shim
选中。引发两个断点 + 一个前置：

1. `torch.cuda.is_available()` False（MLU 非 CUDA）→ megatron
   `assert torch.cuda.is_available()` 炸。前置解决：`import
   torch_mlu.utils.gpu_migration`（`import flag_gems` 已带入）→ cuda API →
   mlu，`is_available()` True。
2. **RNG tracker 设备初始化缺口**：设备初始化前
   `torch.cuda.default_generators` 为空 `[]` → random.py:167
   `default_generators[idx]` IndexError/裸 Generator TypeError。`.pth`
   shim 启动时强制 `torch.ones(1, device="mlu:0")` + synchronize。
3. **device_name 错配**：`PlatformCUDA.device_name()='cuda'` vs 张量
   `device.type='mlu'` → optimizer.py:773
   `TypeError: Wrapped parameters must be one of accelerator ... Received
   torch.mlu.BFloat16Tensor`。shim monkeypatch `device_name→'mlu'`。

容器侧 `cambricon_shim.py`（2066 字节）+ `.pth`（`import cambricon_shim`）三桥承载。
**2066 字节 shim 原样移植 4.4.3→4.7.2，torch 2.7.1 与 2.11.0
语义全等**（两者均无 `mlu.default_generator` attr，三桥验证一致）。
上游候选反馈项（MLF，待提，见矩阵跟踪表 #11）。

其余配方参数缺口（merged wheel config dataclass，与 metax/hygon 同源）：
`--max-position-embeddings`（arguments.py:1131 默认 None 断言）、
`MASTER_ADDR/MASTER_PORT`（env:// rendezvous）。

## post_training（2026-08-22，双后端全 ✅）

post_training = DummyModel + `simple_generate`（surface-imports 全部
megatron.post_training.*，checkpointing.py:7 模块级 `import modelopt.torch`）
exit 0，`output shape = (1, 8)`，0 Traceback。编译器无关路径（sdpa，无
triton kernel）。

**modelopt 安装关键发现（跟踪表 #11 现状补充）**：`nvidia-modelopt==0.45.0`
METADATA 核心依赖 `torch>=2.8`——**0.45.0 根本没有 `[torch]` extra**
（`Provides-Extra` = onnx/hf/puzzletron/dev-*；`nvidia-modelopt[torch]==0.45.0`
pip 仅警告 "does not provide the extra" 后按同解析继续）。

- **4.4.3（torch 2.7.1+cpu < 2.8）**：全依赖解析升级 torch→2.13.0 + 完整
  CUDA toolkit + triton 3.7.1，会替换 vendor torch、破坏 torch-mlu 1.29.2
  （PEP 440 local version：`2.7.1+cpu` 不满足 `>=2.8`）。处置：`--no-deps`
  纯 wheel + 手动补齐纯 Python 依赖（ninja nvidia-ml-py packaging setuptools
  tqdm PyYAML omegaconf pulp pydantic regex rich safetensors scipy requests
  huggingface_hub），torch 未动。`import modelopt.torch` OK（仅
  DeprecationWarning "will drop torch<2.9 support in a future release"）。
- **4.7.2（torch 2.11.0+cpu ≥ 2.8）**：全依赖安装安全，torch/torch-mlu/
  flag_gems 装后复核未变；requests + huggingface_hub 为 modelopt.torch
  plugins import 所需但未在声明依赖中，手动补装。
- **规则（用户定）**：关键包（torch/torch-mlu/triton/flag_gems）一律不升级。

## inference（2026-08-22，双后端全 ✅）

inference = legacy `StaticInferenceEngine` 3 请求 × 8 tokens（prompt_tokens
注入 + detokenize 重写，NullTokenizer 配方自洽）exit 0，0 Traceback。
4.7.2 日志有一条 `torch._inductor.exc.InductorError: No module named
'triton'`（torch_mlu 1.33.1 inductor triton_fusion 插件顶层 import 失败，
捕获后非致命——推理走 sdpa，不触碰 inductor）记录为 observed。

静态 legacy 路径不需要动态批（KV-append 内核设备断言，跟踪表 #2
[MLF #120](https://github.com/flagos-ai/Megatron-LM-FL/pull/120)），故推理
⛔→✅；**动态批推理仍被 #120 阻塞**（矩阵 ⛔ 的原始语义）。

## RL（暂缓）

按验证决策，cambricon 两后端 RL **两端都暂缓**（矩阵 RL 列维持 ⬜）；
待其他后端 RL 路径定案后统一处理。

## 后续追踪

- 平台抽象缺口（#11）已实证待提上游：提 MLF 后容器侧 shim 可取消，重跑
  training/post_training/inference 更新矩阵
- modelopt `[torch]` 关键包升级 hazard 已随本次 wheel 进入 app image 构建面：
  本次 wheel 由集成分支 ci/merge-105-106-107-114 构建（含 [MLF #114]
  (https://github.com/flagos-ai/Megatron-LM-FL/pull/114) 的 `[training]` extra）。
  实测未走 `megatron_core[training]` 安装路径（按不升级关键包约束规避），hazard
  由 modelopt 0.45.0 元数据解析推断；app image 构建需按 torch 版本分派或加保护
- 两个验证容器已清理（2026-08-22，占 NEUWARE 4.4.3/4.7.2 后端）
