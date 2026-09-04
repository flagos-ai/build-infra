# sglang 0.5.18 — NVIDIA cuda13.3（挂起，未闭环）

> **状态：挂起**。验证未跑通，卡在技术路线决策。2026-09-04 audit 完成，结论
> = 跟随 sglang-plugin-FL PR #89 的完整闭包路线（真 flashinfer + 真
> sgl-kernel），放弃我们最初尝试的零依赖 + shim 路线。待 #89 合入后用其 head
> 继续。torch 版本非障碍（可升级）。

## 1. 为什么零依赖路线在真 CUDA 不成立

audit（2026-09-04，h20 实证）结论：

- Qwen3-4B 默认 serve 路径上，flashinfer 的**硬阻塞仅 3 处模块级 import**
  （`fp8_utils.py:188` / `sampler.py:31` / `vision.py:49`，都在 `if is_cuda()` 内
  无 flashinfer 检查）；其余 46 处模块级 import 全被 env 门 / try-except /
  可选模型门护住。给 3 处加 availability 门后，**import 闭包能全过**、能加载
  Qwen3-4B、以 fa3 + pytorch 后端启动（"Application startup complete"）。
- **但模型前向过不去**：CUDA graph 开/关都崩 `not enough values to unpack`
  （qkv 长度 0 / prefill 捕获），根因 = **sgl-kernel-shim 的 `_Dummy` 保真度
  不足**——真 CUDA 上 sgl_kernel 是默认执行路径、有真算子要跑，shim 在 warmup/
  首前向返回空形状。
- 对比：零 sgl-kernel 方案的前提是"硬件算子全走 flag_gems、sgl_kernel 运行时
  符号不被调用"——这在 NPU/PrivateUse1（metax/ascend/cambricon/enflame）
  成立，**在真 CUDA 不成立**。

## 2. 与 sglang-plugin-FL PR #89 的对比（路线决策依据）

| 维度 | 我们的零依赖路线（放弃）| #89 完整闭包路线（采纳）|
|---|---|---|
| flashinfer | 不装（3 处 import 门绕过）| 真装 0.6.17 |
| sgl-kernel | shim（_Dummy 撑不住 CUDA）| 真装 0.4.6.post1 |
| fused-op 接入 | — | 迁 0.5.18 官方 `BaseFusedOp` OOT 注册表 |
| torch | 2.11.0+cu130 | 2.13.0+cu130（可升级，非障碍）|
| 实证 | import 过、前向崩 | H100 Qwen3.6-27B/35B TP=2 全过（~39/142 tok/s）|
| 状态 | 自研、未验证 | 维护方已做（base=main OPEN，等合入）|

**结论**：真 CUDA 是 sglang 主平台，官方闭包（flashinfer + sgl-kernel）是默认
执行路径，shim/hack 顶不了；维护方 #89 已替我们趟完 0.5.18 CUDA 适配，跟随
远便宜于自研补丁。nvidia 线暂停推进，等 #89 合入后以其 head 做 build-infra
侧镜像配套（真 sgl-kernel + flashinfer 入 deps/Containerfile），再走验证。

## 3. 决策记录

- **2026-09-04**：nvidia 走 #89 完整闭包路线；torch 升级不阻塞；零依赖
  shim 方案废弃（真 CUDA 不成立）。
- 待办：#89 合入 → 以 head 配 build-infra nvidia 镜像 → 验证 → 本记录补 E2E
  结论段。
