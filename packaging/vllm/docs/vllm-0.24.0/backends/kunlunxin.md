# vllm 0.24.0 — kunlunxin xre5.37.1

> 本文对应原报告 §13。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 13. kunlunxin（XRE 5.37.1）详细记录（2026-08-23）

> 状态：**验证完成（2026-08-23）**。构建（cp310 empty wheel）、插件移植
> （[VPF #401](https://github.com/flagos-ai/vllm-plugin-FL/pull/401) → 插件 wheel）、app 镜像 serve E2E 三线全通过；serve E2E 覆盖
> flagtree 默认 + triton 侧装双编译器（§13.6/§13.7）。

### 13.1 结论摘要

0.24.0 on kunlunxin **可行且已验证**：构建侧（cp310 empty wheel）与插件侧
（release-0.2 → main 移植）两条路径均已跑通，serve + 推理 E2E 通过——且与
0.20.2 线一致，flagtree 默认 + triton 侧装双编译器均可正常 serve 推理
（§13.6/§13.7）。
两处 0.24.0 结构性 API 变化（GDN 模块重构、fla.ops 平铺化）中，GDN 目标路径
已实测确认；attention 后端类接口经逐项比对基本兼容。FLA patch 目标路径的重指
已在插件分支实现并经混合模型 end-to-end 复核（§13.8.1 / §13.8.6），尚未合并上游。

### 13.2 构建侧：cp310 empty wheel

- pyproject 钉 `torch == 2.11.0`，但 `[tool.uv] no-build-isolation-package =
  ["torch"]` → 实际用 runtime 自带 torch（0.24.0 其余后端同法已验证）。
- kunlunxin 是 **python 3.10** → 需 **cp310 empty wheel**（0.24.0 wheel 绑定
  CPython 小版本，不能复用 cp312 产物，同 [sunrise §11.1](sunrise.md) 先例）。
- 单步安装维持 `--no-deps` → vendor torch 2.9.0+cu129 不被替换。
- ✅ cp310 empty wheel（vllm-0.24.0+flagos）已构建并上传（2026-08-23，
  vllm-wheel 工作流）；app 镜像单步安装线（§13.6）实测通过。

### 13.3 插件移植范围（main 目前零 kunlunxin 引用，全部从 release-0.2 @8236c0a 带回）

| 文件 | 内容 |
|---|---|
| `vllm_fl/dispatch/backends/vendor/kunlunxin/`（整目录） | kunlunxin.py + patch.py + register_ops.py + impl/* + patches/*（直接拷） |
| `vllm_fl/dispatch/config/kunlunxin.yaml` | main 缺此文件（按 platform 名自动加载） |
| `vllm_fl/utils.py` | VENDOR_DEVICE_MAP + supported_device 加 kunlunxin（device_type=cuda） |
| `vllm_fl/platform.py` | block_size=128 分支 |
| `vllm_fl/__init__.py` | `_patch_xpu_get_device` hook |
| `vllm_fl/ops/custom_ops.py` | `apply_kunlunxin_patches()` 调用 |
| `vllm_fl/ops/fused_moe/fused_moe_utils.py` | 3 处：TritonExpertsFL 恒用 + TRITON 回退 + patched fused_experts_impl |

### 13.4 0.24.0 API 适配点（已逐一验证）

- **`mamba/gdn_linear_attn.py` 模块 → `mamba/gdn/` 包** —— 三个 patch fn 需重指目标（名单见下）
- **fla.ops：chunk/fused_recurrent 子包 → 平铺模块** —— ⚠️ 早期记录的「兼容；
  双层 patch（`_fla_ops_lib` + `_fla_chunk_lib`）原样可落」**已证伪**：0.24.0
  无 `vllm.third_party.flash_linear_attention`，旧路径 import 直接
  `ModuleNotFoundError`，被 patch.py 的 try/except 吞成 "Failed to patch FLA
  ops" 告警 —— 必须重指到 `vllm/model_executor/layers/fla/ops`（见下「适配细节」）
- **`from vllm.distributed import get_tp_group`** —— ✅ 可解析（parallel_state
  无 `__all__`，`import *` 带出 def@1349）
- **attention.py 类接口** —— 兼容（细节见下）
- **`CommonAttentionMetadata`** —— ✅ backends/utils.py:37 再导出，无需改
  import
- **`patch_attention_backend_registry`（CUSTOM 注册）** —— 死代码（dispatch 不经
  enum）但 try/except 包裹，保留无害
- **cudagraph** —— 0.24.0 有 `AttentionCGSupport`（backend.py:548）→ 可恢复
  （release-0.2 注释称 0.20.2 没有）
- **`patch_sampler_rng` 签名** —— 0.24.0 以三位置参调用
  `random_sample(probs, generators, use_fp64_gumbel)` → wrapper 需带
  `use_fp64_gumbel=False`（f780db1，旧双参签名会 TypeError）
- **FLA 路径（实测）** —— `vllm/third_party/flash_linear_attention` 已不存在
  （仅剩 flashmla）；实为 `vllm/model_executor/layers/fla/ops` 平铺包
  （chunk.py / fused_recurrent.py）

适配细节：
- GDN：三个 patch fn（patch_fla_ops / patch_fused_gdn_gating / patch_ssm_cache_update）需重指目标；
  0.24.0 引用方为 `mamba/gdn/qwen_gdn_linear_attn.py`（实测存在，`fla_chunk_gated_delta_rule`
  alias + `fused_recurrent_gated_delta_rule_packed_decode`）。
- fla.ops：0.24.0 模型新增 import `fused_recurrent_gated_delta_rule_packed_decode`。
  **实测缺陷**：patch.py 三个 FLA 目标仍指旧路径 `vllm.third_party.
  flash_linear_attention` → 0.24.0 上报 `Failed to patch FLA ops` /
  `Failed to patch _forward_core` 告警；Qwen3-4B（非 GDN）不受影响，但
  Qwen3-Next/GDN 的 chunk/fused_recurrent 替换会失效。
  **修复（已实现并复核，见 §13.8.1）**：三个目标重指
  `vllm.model_executor.layers.fla.ops[.chunk|.fused_recurrent]`，改绑
  `gdn_mod.fla_chunk_gated_delta_rule`（**不是** `_qwen3_next_lib` 上的同名
  alias）—— `ChunkGatedDeltaRule.forward_native` 调用时从 qwen 模块 globals
  解析该名字，只有改绑模块属性才真正改道 chunk 预填路径。
- attention.py：`get_required_kv_cache_layout` 基类默认 None（backend.py:378）→ 0.24.0
  selector 无条件调用，兼容；`get_supported_head_size`（单数 static）需改名
  `get_supported_head_sizes`（复数 classmethod）对齐基类；`get_name()` 返回 "CUSTOM"
  合法无害。

### 13.5 验证风险清单（实测结果）

1. **torch 2.9.0+cu129 vs 0.24.0**（钉 2.11）—— ✅ 单步安装后 serve 启动、
   推理正常，同先例（hygon 2.9.0+das、mthreads、ascend）。
2. **cp310 empty wheel 首建** —— ✅ 构建通过并上传（首个非 cp312 的 0.24.0 wheel）。
3. **flag_gems flagos 路径** —— ✅ whitelist 生效（silu_and_mul / rms_norm /
   rotary_embedding）；op_backends 沿用 release-0.2 无需改。
4. **[VPF #400](https://github.com/flagos-ai/vllm-plugin-FL/pull/400) alpha 修复**（patch.py:401）—— ✅ 0.24.0 路径生效（patched
   forward_decode 应用 + 推理无 NaN/乱码，§13.6）。
5. **triton 侧装编译器路径** —— ✅ 同一 app 镜像 `compiler triton`
   （/opt/triton，vendor triton 3.6.0+gitcd2d6c1b）serve E2E 通过，
   8 patches 全量应用、推理流畅，与 flagtree 路径输出可比（§13.7）。

### 13.6 验证记录（app 镜像 serve E2E，flagtree 路径，2026-08-23）

app 镜像（vllm empty wheel + 插件 wheel 单步安装线 + `vllm-serve` launcher）
在 kunlunxin P800 上的 serve + 推理端到端验证（默认编译器 flagtree 路径；
triton 路径见 §13.7）：

- 镜像 `harbor.baai.ac.cn/flagos-app/vllm0.24.0-kunlunxin-xre5.37.1:
  2.1.2-0.2.0_gf780db1.d20260823`（镜像 tag 中插件版本 `+`→`_`）
- 模型 `/data/models/Qwen3-4B`；serve：`vllm-serve --model
  /data/models/Qwen3-4B --port 8031 --served-model-name qwen3
  --reasoning-parser qwen3 --block-size 128 --gpu-memory-utilization 0.8
  --enforce-eager --trust-remote-code --max-model-len 2048 --dtype bfloat16`
- env（app 镜像 env.app.vllm 四变量，run 需显式 `-e`）：`VLLM_FL_PLATFORM=
  kunlunxin VLLM_FL_PREFER=flagos USE_FLAGGEMS=1 VLLM_FL_FLAGOS_WHITELIST=
  silu_and_mul,rms_norm,rotary_embedding`
- 版本指纹：vllm `0.24.0+flagos`（cp310 empty wheel）；vllm-plugin-fl
  `0.2.0+gf780db1.d20260823`；torch 2.9.0+cu129 / xtorch_ops
  0.1.2935+50a5d6a4 / flag_gems 5.3.4 / numpy 2.2.6 / python 3.10；
  fingerprint `vllm-0.24.0-92673996`
- 补丁全量应用（slot_mapping / attention registry / topk_topp / fused_moe /
  causal_conv1d / fused_gdn_gating / sampler RNG / decode attention），无
  patch_sampler_rng TypeError（f780db1 三参数签名生效）
- 推理：英文流畅；中文任务型 prompt（12/30/40/100 token）全流畅、无 NaN
  乱码、崩溃标记 0（100-token 长生成内容连贯，仅末尾小模型常规重复）
- ⚠️ FLA 补丁告警：patch 目标仍指旧路径
  `vllm.third_party.flash_linear_attention`（0.24.0 已不存在），实为
  `vllm/model_executor/layers/fla/ops` → 重指已在插件分支实现
  （§13.8.1），本镜像未含。
  「非致命」在此仅就 Qwen3-4B 成立（该模型无 GDN 层）；含 GDN 的混合模型
  上镜像原生插件在 engine init 即失败，见 §13.8
- ⚠️ 否定指令型 prompt（"不要用英文，不要用代码"）30-token 出"，，，"标点
  循环 —— 已证与 alpha 无关（同镜像同参数换任务型 prompt 即流畅，
  prompt 内容特性），记 [§16](../index.md) 观察项

### 13.7 验证记录（triton 路径 serve E2E，2026-08-23）

同一 app 镜像（§13.6），仅把编译器切换为侧装 triton 后重跑 serve + 推理，
确认双编译器在 0.24.0 上都可正常推理（与 0.20.2 线先例一致）：

- 容器 `compiler triton` 启动（默认 flagtree 换 triton）：PYTHONPATH 指向
  /opt/triton，`import triton` → **3.6.0**（vendor triton 3.6.0+gitcd2d6c1b，
  与 configs.yaml `triton:` 一致）
- serve 命令同 §13.6，仅 `--port 8032`（flagtree 线 8031），/dev/xpu3 +
  /dev/xpuctrl，env 四变量同
- 启动日志确认 8 个 plugin patches 全量应用，无 sampler RNG TypeError
  （f780db1 三参签名）
- 推理：同三个 completion prompt（1+1= / capital of France / 9.11 vs 9.9）
  输出流畅、无 NaN 乱码，与 flagtree 路径输出质量可比；chat 任务型 prompt
  （长生成）内容连贯
- ⚠️ FLA 补丁两告警同 §13.6（`vllm.third_party.flash_linear_attention`
  旧路径，0.24.0 已不存在）；「非致命」同样仅就 Qwen3-4B 而言（§13.8）；
  重指见 §13.8.1
- 结论：flagtree（默认）与 triton（侧装）双编译器 serve E2E 均通过

### 13.8 混合模型适配与解码乱码（2026-09-15）

§13.6 / §13.7 的验证模型是 Qwen3-4B（dense，**无 GDN 层**）。本节是含 GDN
的混合模型（Qwen3.6-27B / Qwen3.6-35B-A3B）在同一 0.24.0 栈上的结果。

被测镜像：`flagos-app/vllm0.24.0-kunlunxin-xre5.37.1:2.1.2-0.2.0_g344ea82.d20260915`
（engine v0.24.0，torch 2.9.0+cu129，XRE 5.37.1）。§13.8.1–§13.8.5 全部走
`--enforce-eager`；§13.8.6 的验证面另含保留 capture 的 graph 路径。

**13.8.1 镜像原生插件在混合模型上 engine init 即失败**

§13.6 第 124–128 行「FLA 补丁告警非致命」只对 Qwen3-4B 成立。含 GDN 的
Qwen3.6-27B 上，镜像原生插件的 FLA 补丁目标仍指
`vllm.third_party.flash_linear_attention`（0.24.0 已移除），`ModuleNotFoundError`
被 patch.py 的 try/except 吞掉 → GDN 特化未装载 → **engine init 失败**。
把插件换成覆盖层（分支 `feat/kunlunxin-v024`，`patch.py:297-306`）——目标重指到
`vllm.model_executor.layers.fla.ops[.chunk|.fused_recurrent]`——27B 才可启动。
即：**FLA 重指是混合模型启停的分水岭，不是告警清理**。

**13.8.2 解码乱码：与请求序数反相关，逐 step 全 NaN**

同一 prompt 连续发 6 次、其间无其他请求，出现严格 ABAB：奇数次乱码、偶数次正常。
探针定位（`KLXDBG.a3`）：每个乱码请求的**每个** decode step，`self_attn.attn`
的输出全 NaN，而喂给它的全部输入（`qkv_proj` / `q_norm` / `k_norm` / `rotary_emb`）
均有限；prefill 全程干净；layer 0–2 干净；GDN state slot 有限。

判定手段是 `_fp(t) = (abs().max(), sum(), norm(), isfinite().all())`。注意
max 归约**不传播 NaN**——全 NaN 张量的 absmax 落到 `finfo(float32).min =
-3.4028234663852886e+38`。故该数值 ⟺ 全 NaN，是归约伪影，**不是**数据里的值；
早前把它读成 rope sentinel 的解释已否定。

复现面：27B（TP=1）与 35B-A3B（TP=2），flagtree 与 triton 两条编译器路径一致。

**13.8.3 flag 与乱码的相关性随模型几何反号**

同一镜像、同卡、同端口、仅 `USE_RESHAPE_AND_CACHE_FLASH` 有无之别：

| 模型 | 几何 | 无 flag | 有 flag |
|---|---|---|---|
| Qwen3-4B（TP=1，镜像原生插件） | dense | ✅ `......`，distinct-4 0.666 / 0.857 | ❌ `..XXX.`，0.460 / 0.628 |
| Qwen3.6-27B（TP=1，覆盖层插件） | hybrid | ❌ `X.X.X.`，英文 0.078 | ✅ `......`，0.905 / 0.976 |
| Qwen3.6-35B-A3B（TP=2，覆盖层插件） | hybrid MoE | ❌ `X.X.X.`，英文 0.078 | ✅ `......`，0.908 / 0.982 |

上行（dense）与中下两行（hybrid）**反号**：混合模型靠 flag 消乱码，dense
模型被 flag 引入乱码。dense 一格另做了换卡对照（§13.8.4）以排除「卡坏」。
序列列是 6 次同 prompt 连续请求的正常/乱码；混合模型严格交替（`X.X.X.`，
自第 1 次起），dense 不呈交替（`..XXX.`）。distinct-4 = 64 贪心 token 输出的
去重 4-gram 占比，0.078 即 `'Here!!!!!!!…'` 这类跑飞。

flag 消乱码与编译器无关（27B / 35B-A3B）：

| 编译器 | 无 flag | 有 flag |
|---|---|---|
| flagtree | `X.X.X.`（奇数次乱码） | 7/7 干净；探针零非有限张量、零 sentinel |
| triton | 奇数次请求 decode 每步 `self_attn.attn` 全 NaN | 6/6 连贯英文、逐字相同 |

注：`patch.py:439` 的 alpha（`scale × √head_size`）**在当前插件里已经是正确值**，
乱码在 alpha 修好之后依然存在 —— 即 flag 修的是 alpha 之外的另一处
（写入侧 block_table 的 KV offset），与 8/21 hand-off 的判断一致。

**13.8.4 与 8/21 hand-off 的冲突已消解：dense 在 0.24.0 上同样要 flag OFF**

本仓 2026-08-21 hand-off（[`handoffs/kunlunxin-decode-repetition-scale-bug.md`](../../handoffs/kunlunxin-decode-repetition-scale-bug.md)）
记录 Qwen3-4B **移除** flag 后不再乱码 —— 与 §13.8.3 的混合模型结论相反。
该记录出自已被取代的 0.20.2 栈（VPF #268 之前的原生后端、flag_gems 5.3.4
旧插件），故在 0.24.0 上重做配对：同镜像、同端口（8016）、镜像原生插件，
仅 flag 有无之别。

| 臂 | 卡 | 6 次同 prompt | distinct-4（en / zh） |
|---|---|---|---|
| 无 flag | 7 | `......` 全干净、内容连贯 | 0.666 / 0.857 |
| 有 flag | 7 | `..XXX.`，`<think>` 后长串重复 | 0.460 / 0.628 |

首测的两个臂分别落在 5 号卡（flag ON）与 7 号卡（flag OFF），当时「flag 引入
乱码」与「5 号卡坏」是同一个观测。上表把 flag-ON 挪到 7 号卡 —— 即刚跑出干净
文本的那张 —— 乱码照样出现，**卡的因素排除**。

结论：hand-off 的判断在 0.24.0 上**可复现**，dense 4B 要 flag OFF。§13.8.4
与 §13.8.3 不再冲突：flag 的取法取决于模型几何，不存在两全的全局取值。

**13.8.5 厂商默认值就是 flag ON，且厂商测试面只有混合模型 TP=4**

在插件仓（`feat/kunlunxin-v024`）里，`USE_RESHAPE_AND_CACHE_FLASH` 出现五处，
其中三处是**厂商自己把它设成 1**：

| 位置 | 形式 |
|---|---|
| `docker/kunlunxin/Dockerfile:55` | 构建期 `ENV USE_RESHAPE_AND_CACHE_FLASH=1` |
| `.github/configs/kunlunxin.yml:40` | `--env USE_RESHAPE_AND_CACHE_FLASH=1` |
| `tests/platforms/kunlunxin.yaml:71` | `env_defaults:` 里为 `"1"` |
| `.github/scripts/kunlunxin/setup.sh:14` | `${USE_RESHAPE_AND_CACHE_FLASH:?...}` —— **缺失即 CI 报错退出** |

即 flag OFF 不是「默认」，而是**偏离厂商配置**；`?` 展开说明厂商把「设了值」当作前提。

厂商 P800 测试面（`tests/platforms/kunlunxin.yaml:35-38`）只有四个用例：
`qwen3_6/{27b,35b_a3b} × {tp4_eager, tp4_graph}` —— **全部是含 GDN 的混合模型、
全部 TP=4、全部 flag ON**。dense 模型在厂商的测试矩阵里根本不存在。

本仓两侧镜像（base `flagos-base-kunlunxin-xre5.37.1:2.1.2`、runtime
`flagos-runtime-kunlunxin-xre5.37.1:2.1.2`、app
`…:2.1.2-0.2.0_g344ea82.d20260915`）`docker inspect` 均**不带**该变量 →
本仓镜像一律跑在 flag OFF 上，恰是厂商从未测过的那一半。§13.6/§13.7 的
dense-4B 通过，正是因为它落在「flag OFF + dense」这个唯一没人测过但恰好自洽的格子里。

**结论**：这不是「flag 好/坏」的问题，而是**同一份 env 开关承担了两种互斥的
KV 布局约定** —— §13.8.3 的表里三行全部有解、且解不重叠，说明没有任何一个全局
取值能同时服务 dense 与 hybrid。

实测 attention block size：4B=**16**、27B=**784**、35B-A3B=**1056**（TP=2 两
rank 一致），倍率 49× / 66×，而代码里是硬编码的常数 **2** —— 故 `* 2` 不可能
补偿页对齐。抬升来自 vLLM 而非插件：`Platform.update_block_size_for_backend`
先用 `get_preferred_block_size` 取值，再在 `is_hybrid` 时调
`_align_hybrid_block_size` 把 attention 块抬到 mamba 页大小 —— `interface.py:773`
的 "Setting attention block size to …" 与 `:797` 的 padding 行只在混合模型上出现，
dense 4B 无任何 block size 日志。插件 `platform.py:189` 的 `block_size is None`
判据在引擎构建路径上**恒假**：`CacheConfig._apply_block_size_default` 这个
post-validator 在任何 Platform hook 之前就把 `block_size` 定成
`DEFAULT_BLOCK_SIZE=16`，故 `platform.py:196` 的 kunlunxin→128 覆盖是死代码，
「dense 保持 16」是 vLLM 默认值，不是插件给的。

即 `* 2` 补偿的是两个写内核
（`xtorch_ops.reshape_and_cache` vs `xtorch_ops.reshape_and_cache_flash`）
之间的**寻址口径差异**，与页对齐无关；两者在 `attention.py:887` 分叉，
写入的是**同一组** `key_cache`/`value_cache`、**同一份** `slot_mapping`
（`split_kv_cache` 在两条分支上都执行），差别只在 xpu 内核本身。

**13.8.6 修复：写入口径改由模型几何决定（已实现并验证）**

插件改为**按实例解析**：`attention.py` 新增 `resolve_reshape_and_cache_flash()`，
判据取 `model_config.is_hybrid` —— 即 vLLM 自己用来抬 block size 的同一个条件
（§13.8.5）—— 结果缓存后由 `KunlunxinAttentionBackendImpl.__init__` 读入
`self.use_reshape_and_cache_flash`；原先三处读 env 的分叉点（KV 写内核、decode
与 prefix-cache 的块表加倍）全部改读该属性。env 变量保留为**显式覆盖**供厂商 CI
沿用；无 env 时按几何决定，引擎外（单测、离线工具）回落历史默认
（`reshape_and_cache`）且不缓存该回落值。

验证面为 3 几何 × 2 编译器，全部**不设** `USE_RESHAPE_AND_CACHE_FLASH`。
eager 路径（`--enforce-eager`）：

| 臂 | 几何 | 解析结果 | 6 次同 prompt | distinct-4（en / zh） |
|---|---|---|---|---|
| 4B flagtree | dense TP=1 | `reshape_and_cache` | `......` | 0.693 / 0.843 |
| 4B triton | dense TP=1 | `reshape_and_cache` | `......` | 0.649 / 0.858 |
| 27B flagtree | hybrid TP=1 | `reshape_and_cache_flash` | `......` | 0.905 / 0.976 |
| 27B triton | hybrid TP=1 | `reshape_and_cache_flash` | `......` | 0.905 / 0.976 |
| 35B-A3B flagtree | hybrid MoE TP=2 | `reshape_and_cache_flash` | `......` | 0.908 / 0.982 |
| 35B-A3B triton | hybrid MoE TP=2 | `reshape_and_cache_flash` | `......` | 0.908 / 0.982 |

graph 路径（同一镜像、同一覆盖层、同一「不设 env」规则，仅去掉
`--enforce-eager`）：

| 臂 | 几何 | 解析结果 | 6 次同 prompt | distinct-4（en / zh） |
|---|---|---|---|---|
| 4B flagtree | dense TP=1 | `reshape_and_cache` | `......` | 0.972 / 0.990 |
| 4B triton | dense TP=1 | `reshape_and_cache` | `......` | 0.972 / 0.990 |
| 27B flagtree | hybrid TP=1 | `reshape_and_cache_flash` | `......` | 0.905 / 0.976 |
| 27B triton | hybrid TP=1 | `reshape_and_cache_flash` | `......` | 0.905 / 0.976 |
| 35B-A3B flagtree | hybrid MoE TP=2 | `reshape_and_cache_flash` | `......` | 0.908 / 0.982 |
| 35B-A3B triton | hybrid MoE TP=2 | `reshape_and_cache_flash` | `......` | 0.908 / 0.982 |

两条 hybrid 臂在无 env 下复现了 §13.8.3「flag ON」的历史干净数值（此前无 flag
为 `X.X.X.` + 0.078），dense 臂保持「flag OFF」的干净数值，双编译器均通过。
TP=2 的两个 rank 各自独立解析出同一取值，不存在 rank 间口径分歧。

graph 路径的实测模式是 **PIECEWISE** 而非配置里的 `FULL_AND_PIECEWISE`：
`compilation.py` 报 `KunlunxinAttentionBackend` 的 `AttentionCGSupport.NEVER`，
降级为 PIECEWISE；capture 真实执行（每臂 51/51 完成），六臂解析结果与 eager
逐条相同。两种路径的数值关系分两类：hybrid 几何（27B、35B-A3B）graph 与 eager
**完全一致**（0.905 / 0.976、0.908 / 0.982，输出文本逐字相同）；dense 4B 的
graph 数值（0.972 / 0.990）高于 eager（0.693 / 0.843）—— capture 改变了解码
路径，两者都干净，不存在新旧记录互相背书的关系。graph 下同一几何的两条编译器
臂给出相同的长度与 distinct-4，attention 走厂商原生内核、编译器只影响非
attention 算子，capture 把这条差异抹平。

**处置状态**

- 修复位于插件仓分支 `feat/kunlunxin-v024`，为 `d5a3700` 之上的四个提交
  （`attention.py` / `patch.py` / `patches/patch_forward_core.py` /
  `impl/fused_moe/experts_selector.py`）。四个提交目前**只在本地工作树**：
  远端同名分支仍停在 `d5a3700`，未 push，也未提交上游。

- **待办**：上游合并后重建 app 镜像 —— 镜像内置插件仍是旧版，本仓镜像现状
  （不设 env）在建出带修复的镜像前，混合模型仍会乱码。过渡期可在 app env 显式设
  `USE_RESHAPE_AND_CACHE_FLASH=1` 规避（dense 仍不能设，见 §13.8.4）。

- 厂商侧：默认 ON + 测试面只有混合 TP=4（§13.8.5）不变，dense 路径在其 CI 中
  仍无覆盖；本修复使该变量不再是必需的几何开关，建议厂商同步调整默认值与测试面。
