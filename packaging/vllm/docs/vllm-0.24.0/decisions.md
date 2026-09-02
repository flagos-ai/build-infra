# vllm 0.24.0 repack — 版本推进协作问题（决策）

> 本文对应原报告 §7：版本推进协作问题。
> 标准流程见 [playbook.md](playbook.md)，后端验证记录见 [backends/](backends/)。

## 7. 版本推进协作问题

vllm-plugin-FL 项目组在 **`v0.3.0-dev`** 分支上展开 vLLM 0.24.0 适配工作。
在 [VPF #252](https://github.com/flagos-ai/vllm-plugin-FL/pull/252) 处与 main 分叉，尚未合入 main。适配主线：

- [VPF #274](https://github.com/flagos-ai/vllm-plugin-FL/pull/274)（升级 0.20.2→0.24.0）、
- [VPF #294](https://github.com/flagos-ai/vllm-plugin-FL/pull/294)（metax C550 适配）、
- [VPF #308](https://github.com/flagos-ai/vllm-plugin-FL/pull/308)（musa）、
- [VPF #334](https://github.com/flagos-ai/vllm-plugin-FL/pull/334)（mtp）、
- [VPF #338](https://github.com/flagos-ai/vllm-plugin-FL/pull/338)（CUDA stable-ABI wheels）

build-infra 验证用的基线是 main + [VPF #377](https://github.com/flagos-ai/vllm-plugin-FL/pull/377)，vllm-plugin-FL 的正式适配线是 v0.3.0-dev。
需要尽早确定合并路线。

两个分支的重叠/差异：

1. **`_patch_torch_accelerator()`（在 `__init__.py`）vs `accelerator_compat.py`
   —— 功能重复**：
   两边各写了一份 torch.accelerator 补丁。dev 版更严谨：先判断 torch 版本
   （<2.9 才动手）、再逐个查 API 在不在（缺才补）、补全了 6 个 API；
   main 上是早期写的老代码，只补了 `empty_cache` 一个。
   但 dev 版的 `reset_peak_memory_stats` 是直接赋值，**缺我们的 try/except 兜底**
   （torch 2.8 上 mtgpu 显式传 device 会报错）。
   **注意：torch 2.10+metax 上这些 API 原生齐全（实测）→ 两版补丁都不会触发，
   兜底只在 torch 2.8（老 SDK）生效。**

2. **`fa_utils.py` 改用 `flag_gems` 的 `reshape_and_cache_flash`，
   dev 仍用 `ops.reshape_and_cache_flash` —— dev 没处理 empty wheel 场景**：
   dev 分支 + empty wheel 组合未验证（问题 4 同因，
   0.20.2 [VPF #333](https://github.com/flagos-ai/vllm-plugin-FL/pull/333) 的修法没 upstream 过去）。

3. **`vllm024_compat.py`（问题 3/5/6 的 4 个补丁），dev 上不存在**：
   项目组没有使用过 3.1.0 的编译器，验证路径不同。
   我们的 4 个修复要不要 upstream 到 dev，待确认。

4. **dev 独有的 `chunk_delta_h.py` 的 USE_EXP2**（0.24.0 上游内核签名新增的参数）：
   我们没遇到的坑，验证路径未覆盖。

**待定事项：**
- [ ] **确认 0.24.0 正式发布线**：main（+ 我们补丁）还是 v0.3.0-dev？
      如果以 dev 为基线，[§4](backends/metax.md) 的验证要在 dev 分支上重验。
      **[§6](backends/nvidia.md) 的 NVIDIA 验证已在 dev 基线上完成（空模式、零 patch、
      双编译器全过）**，证明 dev 分支在 CUDA 上可直接交付；metax 侧则需要确认 3.0.0
      编译器问题的 4 个补丁是否 upstream。
- [ ] `_patch_torch_accelerator` 与 `accelerator_compat.py` 去重：
      保留哪个版本；是否把 reset 的 try/except 兜底 backport 到 dev。
- [ ] 确认 dev 分支在 triton 3.0.0 路径是否缺问题 3/5/6 的修复（serve 冒烟即知）。
- [ ] dev 分支 + empty wheel：`reshape_and_cache_flash` 是否同样报错
      → flaggems 方案是否要 upstream 到 dev。
- [ ] 我们的验证路径补测 `USE_EXP2` 相关内核（chunk delta，Qwen3-Next/GDN 类模型）。

---

## 8. 跨后端建议：flag_gems ConfigCache 按编译器隔离

**背景（2026-09-01 metax 实证，2026-08-28 sglang 线同坑先踩）**：

flag_gems 的 SQL ConfigCache DB 名（`TunedConfig_<vendor>_triton_<ver>.db`）与
cache key（source hash + shape）都**不含编译器身份**。同一 vendor 同 triton 版本下，
F（flagtree）/T（triton）共用同一 DB：

- F 路径调优写入的 config（metax：BLOCK_M=8/1，Qwen3-4B qkv_proj 6144×2560；
  sglang：BLOCK_SIZE_M=8，Qwen3-0.6B）对 vendor triton **不可编译**；
- T 路径 cache-hit 盲启动编译直接硬崩（`PassManager::run failed`）——
  **cache-miss 的 bench() 有 per-config try/except（失败记 inf 重选），
  cache-hit 的 run() 没有**；
- app 镜像**不携带**该缓存（`/root/.flaggems/config_cache/` 运行时懒创建在容器
  可写层），故无需重建镜像。

**建议（对所有双编译器 runtime 镜像适用，非 metax 个案）**：
serve/验证配方按编译器隔离缓存，`FLAGGEMS_DB_URL=sqlite:////tmp/..._<compiler>.db`，
或切换编译器前删除默认 DB。结构上所有 runtime 镜像都是 /flagos + /opt/triton 双编译器。

**上游修复**：[FlagGems #5829](https://github.com/flagos-ai/FlagGems/pull/5829)
（`LibTuner.run` 自愈：config_from_cache 专用标志 + 删中毒条目 + retune_from_scratch，
OPEN 未合并）。合并进新 flag_gems wheel 后，上述隔离降级为防御性写法。
