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
