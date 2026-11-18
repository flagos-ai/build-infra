# vllm 0.24.0 — mthreads musa5.2.0

> 本文对应原报告 §8。标准流程见 [`playbook.md`](../playbook.md)，
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
  这是 **0.24.0 全部无 torchvision OOT 后端（cambricon×2、hygon、ascend×2）
  的通用前置修复**。
- **早期 serve "零补丁" 的诚实注记**：5.2.0 首轮（§8.2）的 serve 成功，实际
  依赖节点侧就地改写 site-packages 的 `kernel_warmup.py`
  （`/tmp/patch_minimax_warmup.py`，不可复现），不是 wheel 内建能力；重建镜像的
  新容器不补丁必崩（torchvision ImportError）。§8.2 的"零补丁"仅指**插件**
  零补丁，vllm 在树补丁一直存在。可复现路径 = 插件 guard
  （[VPF #386](https://github.com/flagos-ai/vllm-plugin-FL/pull/386)），重建镜像
  后已按此路径重验（§8.4）。

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
  → kernel_warmup（插件 guard 门控，见 §8.3）→ `Application startup complete`。
  插件换装是 editable install（`.pth` + finder），`vllm-plugin-fl==0.0.0`；
  插件无 `.so`（csrc 仅 ascend/cuda，`vllm_fl._C` import 为 try/except 门控）。
- **推理**：8031 端口两次请求均输出连贯 chain-of-thought（DeepSeek-R1
  模型正常思考）。✅ E2E 通过。

---
