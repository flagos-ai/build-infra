# vllm 0.24.0 — mthreads musa5.2.0 / musa4.3.6

> 本文对应原报告 §8 与 §9。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 8. mthreads（MUSA 5.2.0）详细记录

- venv：`/flagos`（cpython-3.10）
- 模型：`/data/DeepSeek-R1-0528-Qwen3-8B-FlagOS`
- 端口：8031

### 8.1 构建 + 安装

- **pin_indirect 落地**：`packaging/vllm/config.yaml` 增加
  `pin_indirect: {xgrammar: "0.2.3"}`。0.24.0 对 xgrammar 的自身依赖自相矛盾
  （0.2.5 需要 torch/transformers 版本约束在 Runtime 矩阵上无法满足），
  xgrammar 锁到 0.2.3（`transformers>=4.38.0`，无上界，兼容 transformers 5.15.0），
  repack 后 METADATA 为 `xgrammar==0.2.3+flagos`。
- **单步安装**（厂商索引 + 阿里云镜像 extra）：
  `/flagos/bin/pip install --index-url
  https://resource.flagos.net/repository/flagos-pypi-mthreads/simple/
  --extra-index-url https://mirrors.aliyun.com/pypi/simple vllm==0.24.0+flagos`
  ✅ 通过，命中 `+flagos` wheel，无 torch 侧漏。

### 8.2 插件基线：v0.3.0-dev 零补丁（替代首轮的 main+8 处补丁）

**首轮验证**在 main 分支（db9afd6）+ 8 处本地补丁上完成（见下方历史清单）。
随后将容器插件换成 **v0.3.0-dev head（fbc115d）** 重跑 E2E：

- **结果：零补丁，全部通过。** 8 处 drift 修复在 v0.3.0-dev 上均有官方实现
  （已合入 [VPF #274](https://github.com/flagos-ai/vllm-plugin-FL/pull/274) /
  [VPF #294](https://github.com/flagos-ai/vllm-plugin-FL/pull/294) /
  [VPF #308](https://github.com/flagos-ai/vllm-plugin-FL/pull/308) /
  [VPF #338](https://github.com/flagos-ai/vllm-plugin-FL/pull/338) /
  [VPF #376](https://github.com/flagos-ai/vllm-plugin-FL/pull/376)），其中：
  - InputBatch 签名、`use_uniform_kv_cache` 单参 → model_runner.py:717 / :7300（[VPF #274](https://github.com/flagos-ai/vllm-plugin-FL/pull/274)）
  - FusedMoE 工厂函数注入 `_patch_fused_moe_factory`（custom_ops.py）
    → 替代我们的 `inspect.isclass` 门控 + OOT_OPS + oracle 方案
  - MarlinExperts / TritonExperts / rocm_aiter 新路径 → fused_moe_utils.py:19、router.py:9
  - flashinfer 惰性解析 → fused_moe_utils.py:171 内联
  - DeepSeek-V4：head 整体移除 deepseek_v4 模块族（与 0.24 上游同步），我们的门控 patch 无意义
- serve 启动链：OpManager **10 ops / 14 implementations**（head 重构后的 dispatch，
  规模小于 main 线的 35/65）→ attention_backend fallback `default.flagos` → `vendor.musa`
  → 权重加载 → `Application startup complete`
- 推理：chat/completions 输出连贯 CoT（DeepSeek-R1 正常思考）；completions greedy 输出连贯
- **非致命差异**：usage_lib 遥测线程报 `Cannot re-initialize MUSA in forked subprocess`
  （vllm 侧 `platform_utils` 用 fork 子进程查设备属性，MUSA 运行时 fork 后不可重初始化；
  仅遥测失败，不影响服务）。main+补丁基线无此报错，head 出现 —— 未追因，列入遗留。
- **原始 completions 直给 R1 模型 + temperature 0.6 出现整段重复回声**：是未套 chat
  模板的 R1 模型行为伪影，非插件缺陷（chat/completions 与 greedy 均正常）。

**历史记录：首轮 main 分支的 8 处 drift 修复（已被 v0.3.0-dev 官方实现取代，不再需要）**

MUSA 平台走插件路径（`PlatformFL` → device_type `musa`、dist_backend `mccl`），
0.24.0 的上游重构让插件暴露 8 处不兼容（main 线逐一修复）：

1. **`InputBatch.__init__` 签名变化**（`model_runner.py` 两处调用点）：
   0.24.0 删除 `pin_memory`、`is_spec_decode: bool` 改名 `num_spec_tokens: int`、
   新增 `reasoning_config`。插件已自算 `self.num_spec_tokens`，直接适配新签名。
2. **`use_uniform_kv_cache` 变 `@staticmethod`**：0.24.0 签名
   `use_uniform_kv_cache(attn_groups)`，`cache_dtype` 参数删除
   （统一布局决策移入 kv_cache_config）。调用点删掉 `cache_dtype` 实参。
3. **`FusedMoE` 从 PluggableLayer 子类变成工厂函数**（`fused_moe/layer.py`）：
   0.24.0 起 `def FusedMoE(...) -> MoERunner`，`class FusedMoEFL(FusedMoE)`
   无法定义。OOT MoE 层按 `inspect.isclass(FusedMoE)` 门控，
   非类时 `FusedMoEFL = None`，MoE 回退上游 oracle（
   `_patch_unquantized_moe_oracle` 无条件生效）。
4. **`MarlinExperts` 迁到 `fused_moe/experts/marlin_moe.py`**：
   `mxfp4_marlin.py` 的 import 改为新路径优先、旧路径 try/except 兜底。
5. **`TritonExperts` 迁到 `fused_moe/experts/triton_moe.py`**：同模式。
6. **`rocm_aiter_grouped_topk` 迁到 `fused_moe/router/grouped_topk_router.py`**：
   同模式。
7. **`get_flashinfer_moe_backend` 从 flashinfer_utils 删除**：改为惰性解析。
8. **DeepSeek-V4 OOT wrapper 门控**：`cublas_gemm_bf16_bf16_fp32`
   （`vllm.model_executor.layers.utils`）在 0.24.0 删除，0.24.0 上
   DeepSeek-V4 走上游，OOT wrapper 整体 try/except 门控。

### 8.3 上游 vllm 在树补丁（非插件，MUSA 验证的唯一残余补丁）

- **`kernel_warmup` 无条件 import `minimax_m3_msa_warmup`**：
  import 链到达 `torchvision.transforms`（`transformers_utils/processors/
  minimax_m3.py`），而 OOT Runtime 不装 torchvision（装它必然覆盖厂商匹配的
  torch 矩阵）。该 warmup 对非 MiniMaxM3 模型是 no-op。
- **归属已定：进插件调用侧（[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)）** —— `kernel_warmup` 调用点在插件
  `vllm_fl/worker/worker.py`，在调用处 `try/except ImportError` 门控即可，
  不改 vllm wheel（wheel 保持与上游逐字节一致），也不在镜像里装 torchvision。
  这是 **0.24.0 全部无 torchvision OOT 后端（cambricon×2、hygon、ascend×2、
  mthreads×2）的通用前置修复**，见 §9.4。
- **早期 serve "零补丁" 的诚实注记**：5.2.0（§8.2）与 4.3.6 首轮（§9.2）
  的 serve 成功，实际依赖节点侧就地改写 site-packages 的
  `kernel_warmup.py`（`/tmp/patch_minimax_warmup.py`，不可复现），不是 wheel
  内建能力；重建镜像的新容器不补丁必崩（torchvision ImportError）。
  §8.2/§9.2 的"零补丁"仅指**插件**零补丁，vllm 在树补丁一直存在。
  可复现路径 = 插件 guard（[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)），重建镜像后已按此路径重验（§9.4）。

### 8.4 验证过程要点

- **stale `__pycache__` 陷阱**：插件源码打补丁后必须
  `find /opt/vllm-plugin-FL -type d -name __pycache__ -exec rm -rf {} +`，
  否则 serve 进程 import 的是旧字节码（曾把已修好的 DeepSeek-V4 门控
  问题再次以 `cublas_gemm` ImportError 形式暴露）。换 v0.3.0-dev 时同样
  先清 `__pycache__` 再 `pip install -e . --no-build-isolation`
  （head 构建依赖 `torch>=2.7.1`、`scikit-build-core==0.11`、`cmake`，
  必须 `--no-build-isolation`，否则 pip 隔离环境会从公共源拉 torch 覆盖矩阵）。
- **serve 启动逐级打通**（v0.3.0-dev + torchvision guard）：EngineCore 初始化
  （`device_config=musa`、`backend=mccl`，DP/PP/PCP/TP rank 分配）→ 插件
  OpManager（10 ops / 14 implementations，attention_backend `default.flagos`
  → `vendor.musa`）→ 权重加载（safetensors 2/2，约 5 秒）→ KV cache 初始化
  → kernel_warmup（插件 guard 门控，见 §9.4）→ `Application startup complete`。
  插件换装是 editable install（`.pth` + finder），`vllm-plugin-fl==0.0.0`；
  插件无 `.so`（csrc 仅 ascend/cuda，`vllm_fl._C` import 为 try/except 门控）。
- **推理**：8031 端口两次请求均输出连贯 chain-of-thought（DeepSeek-R1
  模型正常思考）。✅ E2E 通过。

---

## 9. mthreads（MUSA 4.3.6）详细记录

- torch 2.9.0+musa.4.3.6
- venv：`/flagos`（cpython-3.10）
- 插件：v0.3.0-dev head + torchvision guard（[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)），editable install 于 `/opt/vllm-plugin-FL`
- 模型：`/data/DeepSeek-R1-0528-Qwen3-8B-FlagOS`
- 端口：8031

### 9.1 构建 + 安装

同 §8.1 —— 单步安装 `vllm==0.24.0+flagos`（cp310 wheel，命中 `+flagos`
wheel，无 torch 侧漏）；`pin_indirect: {xgrammar: "0.2.3"}` 同。

### 9.2 插件基线：v0.3.0-dev + torchvision guard

插件 v0.3.0-dev head（fbc115d），除 **torchvision guard**（§8.3/§9.4，插件
[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386) 的调用侧补丁）外零补丁。serve 启动链与 5.2.0 一致：
OpManager **10 ops / 14 implementations** → attention_backend fallback
`default.flagos` → `vendor.musa` → 权重加载 → `Application startup complete`。
非致命遥测 fork 报错（`Cannot re-initialize MUSA in forked subprocess`）与
§8.2 相同，不影响服务。

**重建镜像复验（2026-08-17）**：configs bump（[build-infra #414](https://github.com/flagos-ai/build-infra/pull/414)）后重建的镜像
（flagtree 0.6.1 烘焙于 `/opt/flagtree`），新容器首次 serve 因 torchvision
ImportError 崩溃（§9.4 首段）；应用插件 guard 后 F/T 双路径均重验 ✅
（F 见 §9.3，T 见 §9.4 末段）。早期首轮 serve 记录在 §9.3 的 0.6.0/0.6.1
实验中，仅作根因证据。

### 9.3 编译器路径判定

**T 路径 ✅**（vendor triton 3.6.0+git89458660）：

- 触发算子：YaRN rotary-embedding `_compute_inv_freq` 中的
  `base ** pos_freqs`（base=1000000.0，1024 元素 MUSA float 张量）→
  flag_gems `pow_scalar` → `pow_func_scalar_tensor_kernel_rank_1_bptr_t1024`。
  该内核在 **vendor triton 下编译通过**（op 级 repro 输出
  `OK [1.0, 1.01358..., 1.02735...]`）。
- serve E2E ✅（重建镜像复验 2026-08-17）：`Application startup complete`；
  completions greedy 与 chat CoT 均连贯；指纹 `vllm-0.24.0-5936039f`
  （5.2.0 为 `vllm-0.24.0-423da8ca`）。
- 验证模型为 DeepSeek-R1-0528-Qwen3-8B-FlagOS（该平台无 Qwen3-4B），
  矩阵"Qwen3-4B"约定在此单元格不适用；原始 completions 直给 R1 模型 +
  temperature 0.6 的整段重复回声是模型行为伪影（同 §8.2）。

**F 路径 ✅（flagtree 0.6.1 烘焙镜像，重建后复验）**：

1. **0.6.0 的失败（双层根因，镜像原状）**：
   a. **flag_gems 拦截 pow → flagtree codegen 失败**：`base ** pos_freqs` →
      `__rpow__` → flag_gems `pow_scalar` → `pow_func_scalar_tensor_kernel_rank_1_bptr_t1024`
      （pow.py:61:34，`tl.exp2`）→ flagtree 0.6.0+mthreads3.6 发出向量化
      `LLVM ERROR: Cannot select: v2f32 = fexp2` → vendor llc
      （`/usr/local/musa/bin/llc -march=mtgpu -mcpu=mp_31`）无法选择 → SIGABRT。
      报错前一行是 `llc` failed with error code -6。
   b. **黑名单排除 pow 后落入损坏的原生 torch 路径**：
      `VLLM_FL_FLAGOS_BLACKLIST=pow_scalar`（**正确排除名** —— flag_gems
      `config_filter` 按 Python 函数 `__name__` 匹配，不是 aten schema 名
      `pow.Scalar`；`enable(unused=["pow"])` 不生效）→ pow 不再被 flag_gems
      拦截（崩溃位置从 flag_gems pow.py 变为 `torch/_tensor.py:1113` 的
      `__rpow__`）→ 原生 `torch.pow(other, self)` →
      `RuntimeError: tensor.device().is_cpu() INTERNAL ASSERT FAILED at
      pybind_utils.cpp:590` —— torch 2.9.0+musa.4.3.6 无法处理 Python float
      底数 ** MUSA 张量指数。
2. **0.6.0→0.6.1 实验（2026-08-17）确认根因**：同一容器手动替换 flagtree
   为 **0.6.1+mthreads3.6**（whl `flagtree-0.6.1+mthreads3.6-cp310-cp310-...`，
   安装到 `/opt/flagtree061` 后整体替换 `/opt/flagtree`，原 0.6.0 保留在
   `/opt/flagtree060`）后：
   - op 级 repro 通过：同一 `base ** pos_freqs` 内核编译成功，输出
     `OK [1.0, 1.01358..., 1.02735...]`（0.6.0 下同脚本 SIGABRT）；
   - serve E2E ✅：`Application startup complete`（OpManager 10 ops / 14
     impls，rms_norm / silu_and_mul 走 `default.flagos`），completions greedy
     + chat CoT 均连贯；指纹 `vllm-0.24.0-5936039f`（同 T 路径，同容器同插件）。
3. **烘焙镜像复验（2026-08-17，configs bump [build-infra #414](https://github.com/flagos-ai/build-infra/pull/414) 已合并）**：configs.yaml
   bump 后重建的镜像把 **0.6.1+mthreads3.6 烘焙于 `/opt/flagtree`**（不再
   手动替换）。F 路径（`compiler flagtree`）+ 插件 torchvision guard 下
   serve 到 `Application startup complete`、completions greedy + chat CoT
   均连贯、指纹 `vllm-0.24.0-5936039f`，与 T 路径完全一致。✅

结论：`self.base ** pos_freqs` 在 flagtree **0.6.1** 下可用 —— 0.6.0→0.6.1
即修复（不再对 `tl.exp2` 发出 vendor llc 不可选择的 `v2f32 = fexp2`）。
configs bump（[build-infra #414](https://github.com/flagos-ai/build-infra/pull/414)）已合并、镜像已重建，4.3.6 F 路径对应交付物验证完成；
5.2.0 自始即 0.6.1（§8，F 路径 ✅），mthreads 平台 F 路径全线一致。

### 9.4 torchvision guard：0.24.0 通用 OOT 前置（插件 [VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)）

- **现象**：重建镜像的新容器（flagtree 0.6.1 烘焙）首次 serve 在 EngineCore
  init 崩溃 —— vllm 0.24.0 `kernel_warmup()` 无条件 import
  `minimax_m3_msa_warmup`，import 链到达 `torchvision.transforms`
  （§8.3），OOT runtime 不装 torchvision → `ImportError: No module named
  'torchvision'`。
- **为什么 5.2.0 / 4.3.6 早期 serve 没崩**：那些容器在节点侧就地改写
  site-packages 的 `kernel_warmup.py`（`/tmp/patch_minimax_warmup.py`）——
  不可复现，不属于任何 wheel。**重建镜像的新容器即复现**，排除了
  "wheel 自带补丁" 的误判。
- **修复（插件调用侧，[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)）**：`kernel_warmup(self)` 调用处
  `try/except ImportError` 门控 + warning（warmup 对非 MiniMaxM3 是 no-op）。
  不改 vllm wheel（与上游逐字节一致），不装 torchvision（不污染厂商 torch
  矩阵）。**影响全部无 torchvision OOT 后端**：cambricon×2、hygon、
  ascend×2、mthreads×2。
- **复验**：同一新容器应用 guard 后（`/opt/vllm-plugin-FL/vllm_fl/worker/
  worker.py`，与 [VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386) 逐字相同，compile OK）→ F/T 双路径 serve 均到
  `Application startup complete`、推理连贯、指纹 `vllm-0.24.0-5936039f`。

---
