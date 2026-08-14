---
name: megatron-verification-state
description: megatron 应用镜像验证阶段的状态：已定决策、待决事项、文件状态、任务状态（2026-08-14 结束点）
metadata: 
  node_type: memory
  type: project
  originSessionId: d7f830af-2108-4f39-aba9-825e3ddd911e
  modified: 2026-08-14T09:00:00.000Z
---

# Megatron 应用镜像验证阶段 — 状态快照（2026-08-13 收工点）

**阶段:** hygon25 验证期（build-infra 的 megatron 打包 + 应用镜像工作）。

## 已定案（今天确认的决策）

1. **交付形态 = 应用镜像**：wheel 单步安装进 `flagos-runtime-{vendor}-{backend}` 镜像，用户直接跑训练服务。**repo checkout 交付 = 王八蛋方式，不可接受。**
2. **单 wheel，不做多组件**。应用场景（训练/后训练/RL/推理）归并进一个 wheel，场景是镜像内能力、不是镜像种类。
3. **编译器归并规则**（用户原话定性）：**验证面不归并**——每个后端 × 两个编译器（flagtree/triton）都要验证；**交付面归并**——每后端只交付能用的编译器，不能用的屏蔽（不设默认/不装）。
4. **hygon 编译器 mask**：flagtree 3.6.0 ✗（屏蔽，clang-17 拒 5 个 `-mllvm` flags → HSACOError），vendor triton 3.3.0 ✓（交付，`llvm.translate_to_asm()` 直接出码）。详见 [[hygon-compiler-mask]]。
5. **vendor triton 复跑成功**：两种验证形态均 exit 0，**不再需要 jit.py 补丁和 `--disable-jit-fuser`**（这两者是 flagtree 缺陷的规避，不是平台必需的）。loss 9.1295→8.8622（完整训练服务）。
6. **打包范围扩大方向**：pyproject include 已改（core+plugin+training+legacy），**未提交、未构建、未验证**。决策 3 未定案（见下）。
7. **psutil 缺口定性**：代码是 NVIDIA 上游（ADLR/Megatron-LM）写的，本 fork（megatron-lm-fl）**继承**该缺口，PR #106 修复（声明进 pyproject）。
8. **打包环境 = runtime 镜像**（2026-08-14 用户定）：不再依赖设想中的 megatron-builder-py* 镜像（从未构建过——#368 时设想，CI 因此失败 `base name should not be blank`）。runtime 镜像自带正确 python 版本 + 关键运行时包，打包过程不变（clone → patch → stamp → pip wheel → gate），且打包环境 = 交付环境 → 装完 wheel 即可做依赖面安全验证。
9. **repack facility 已删**（2026-08-14 用户同意后 git rm）：`packaging/megatron/repack/` 唯一正事是剥 torch（vllm sdist 模式才需要）；megatron 是 fork 源码模式，**torch>=2.6.0 声明保留不动**（全后端 vendor torch ≥2.7.1，pip 解析天然满足），repack 无活可干。verify 脚本移至 `packaging/megatron/verify/verify-megatron-backend.sh`。

## 待决事项（用户需权衡）

- **决策 6（TODO，2026-08-14 用户记）: 跨后端共享假设验证**——一个 cp310 wheel 是否可在全部 py3.10 后端共享。路径：**先按 hygon 打**，mthreads 上**假设可用**，**待所有 py3.10 后端验证通过才下结论**；py3.11 / py3.12 同样各过一遍。**最终决策**：是否需要预装三个 python 版本的 megatron builder 镜像、一次打三个包；还是假设太乐观、必须每后端重新打包。

- **决策 3**: wheel 范围——training+legacy 还是全包（再纳入 inference/post_training/rl）？归并讨论倾向全包，但用户纠正了归并框架（编译器验证面不归并），全包未最终定案。
- **决策 4**: 入口脚本（pretrain_gpt.py 等）在 wheel 里 vs 镜像层 COPY —— 未定。
- **决策 5**: PR（扩大范围）时机——现在提还是验证后再提 —— 未定。
- **产品决策**: 一个镜像干所有事 vs 多个应用镜像 —— 权衡中，未定。
- **vllm 关系（未决）**: 用户称"megatron 的推理依赖 vllm"，但全树 grep 零真实 vllm import（仅 `megatron/core/inference/async_stream.py` 有 "adopted from vllm" 注释）。用户打断过我下结论，**不能断言任一方**；可能指 checkpoint→vllm serve 的流程衔接。

## 文件状态

- `/Users/baai/work/Megatron-LM-FL/pyproject.toml` — **已提交**（commit ba22f6b67，分支 feat/wheel-full-scope）：packages.find.include 扩到 training+legacy+rl+post_training+inference，py-modules 收编 9 个顶层入口文件（gpt_builders/mamba_builders/model_provider/pretrain_gpt/pretrain_bert/pretrain_mamba/pretrain_t5/pretrain_vlm/train_rl）。**PR #107 OPEN**（https://github.com/flagos-ai/Megatron-LM-FL/pull/107），3 个 CI check queued（fork 侧）。repo 工作树 clean。
- `/Users/baai/work/build-infra/findings/megatron-hygon25-e2e.md` — 今天已更新：①Status 表去掉 PART A/B 命名改"wheel-only 训练循环"/"完整训练服务"，②新增"打包背景"节（wheel 范围继承上游、缺 training 是若干发现根因、repo checkout 验证的原因），③"上游"歧义明确（代码来源=ADLR/Megatron-LM，提交/反馈目标=flagos-ai/Megatron-LM-FL），④§2.1 编译器 mask 表，⑤§4 `--disable-jit-fuser` 标注仅 flagtree 需要。
- **报告位置（2026-08-13 晚移动）**：`/Users/baai/work/build-infra/packaging/megatron/docs/megatron-hygon25-e2e.md`（不在 findings/ 下；用户指定放 packaging/megatron/docs/）。
- **runtime 镜像层待办**：hygon DTK 26.04 的默认编译器是 flagtree（错误默认）——需在 runtime 镜像层改默认 vendor triton 或移除 flagtree。属 runtime 仓库工作。

## 任务

- **#15 in_progress**: 扩大 wheel 打包范围到 training+legacy+rl+post_training+inference 并重新验证（pyproject 已提交、PR #107 已开；余：定决策 3/4/5、重建 wheel、重跑四场景 E2E——单步安装 + 直接跑入口脚本无需 repo checkout）。
- **#16 pending（决策 6 TODO）**: 跨后端共享假设验证——runtime 镜像作打包环境打 cp310 wheel，先 hygon 打、mthreads 假设可用，全 py3.10 后端验证通过才下结论"一个 wheel 够用"；py3.11/py3.12 同样各过一遍。最终决策：预装三 python 的 builder 镜像一次打三个包 vs 每后端重新打包。
- **#14 pending**: 验证 `megatron-core[training]` extra 是否引入 torch/triton 递归覆盖（transformers/accelerate 声明 torch；候选修复 `torch; sys_platform == 'never'` override-dependencies 先例）。

## 相关

- 上游 PR：#105（§1.1 megatron.training import 修复）、#106（§1.2 psutil 声明）。
- E2E 脚本：`/tmp/hygon25-megatron-e2e.sh`（flagtree 基线）、`/tmp/hygon25-megatron-e2e-triton.sh`（vendor triton 变体）。
- 持续约束见 [[work-constraints]]。
