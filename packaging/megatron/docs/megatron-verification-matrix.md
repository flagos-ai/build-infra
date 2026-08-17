# Megatron 场景 × 编译器 × 后端 验证矩阵

> 规划工具，随验证推进更新。每单元格为对应后端 runtime 镜像 + 一步安装 wheel 后，对应场景入口跑通的验证。
> wheel 打包范围：core+training+legacy+rl+post_training+inference（全范围 wheel，MLF PR #107 feat/wheel-full-scope）；hygon 四场景已用该 wheel 验证（vendor triton 线）。

## 状态图例

| 符号 | 含义 |
|---|---|
| ✅ | 已验证通过（E2E exit 0） |
| ❌ | 已屏蔽（编译器不可用，不设默认/不交付） |
| ⛔ | 挂起（需先解决上游阻塞） |
| ？ | 成功概率不确定（缺 vendor 变体依赖） |
| ⬜ | 待验证 |
| — | 该后端无此编译器 |

列名后缀：T = Triton 编译器，F = FlagTree 编译器。

> 注：hygon 的 F 列为 ⬜ 而非 ❌——flagtree 编译级可用（DTK LLVM 包后，
> 与 triton 3.5.1 同源 dtk 特判），但 megatron 场景级 E2E 均未在 flagtree 下
> 验证，可能有问题，待按场景复测（§1.4 `--disable-jit-fuser` 是否仍需同测）。

## 矩阵

| 厂商     | 后端          | 训练(T) | 训练(F) | 强化学习(T) | 强化学习(F) | 后训练(T) | 后训练(F) | 推理(T) | 推理(F) |
| -------- | ------------- | ------- | ------- | ----------- | ----------- | --------- | --------- | ------- | ------- |
| 英伟达   | CUDA 12.8     | ⬜      | ⬜      | ⬜          | ⬜          | ⬜        | ⬜        | ⛔      | ⛔      |
| 英伟达   | CUDA 13.3     | ⬜      | ⬜      | ⬜          | ⬜          | ⬜        | ⬜        | ⛔      | ⛔      |
| 昇腾     | CANN 8.5.0    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 昇腾     | CANN 9.0.0    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 寒武纪   | NEUWARE 4.4.3 | ⬜      | —       | ⬜          | —           | ？        | —         | ⛔      | —       |
| 寒武纪   | NEUWARE 4.7.2 | ⬜      | —       | ⬜          | —           | ？        | —         | ⛔      | —       |
| 燧原     | TOPS 1.9.10   | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 燧原     | TOPS 1.10.6   | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 海光     | DTK 26.04     | ✅      | ⬜      | ✅          | ⬜          | ✅        | ⬜        | ✅      | ⬜      |
| 天数智芯 | COREX 4.4.0   | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 昆仑芯   | XRE 5.37.1    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 沐曦     | MACA 3.7.2.1  | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 沐曦     | MACA 3.8.1.3  | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 摩尔线程 | MUSA 4.3.6    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 摩尔线程 | MUSA 5.2.0    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 进迭时空 | SPACEMIT      | ⬜      | —       | ⬜          | —           | ？        | —         | ⛔      | —       |
| 曦望     | TANGRT 1.2.0  | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 平头哥   | PPU 2.0.0     | ⬜      | —       | ⬜          | —           | ？        | —         | ⛔      | —       |
| 清微智能 | TSM 260610    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |

## 编译器覆盖现状（configs.yaml 2026-08-14）

- **双编译器**（15 backend）：nvidia×2, ascend×2, enflame×2, hygon, iluvatar, kunlunxin, metax×2, mthreads×2, sunrise, tsingmicro
- **仅 triton**（4 backend）：cambricon×2, spacemit, thead

## 已验证/已知事实

- **hygon training**：vendor triton 3.3.0 ✅（E2E exit 0，loss 9.1295→8.8622）。
  flagtree 3.6.0 **编译级可用**（DTK LLVM 包 PR #403 后，与 triton 3.5.1 同源
  dtk 特判 aillvm/clang-18；flag_gems mm/addmm/mm-bf16 全过 diff 0.0）但
  **场景级 E2E 未在 flagtree 下验证**——训练(F)=⬜。详见
  [[megatron-hygon25-e2e.md]] 与 [[memory/hygon-compiler-mask]]。
- **hygon flagtree 场景级状态（2026-08-17 更正）**：曾判"屏蔽"系旧容器缺
  DTK LLVM 包所致，已证伪；现四场景 F 列一律 ⬜——编译级可用，场景级未验证，
  "可能有问题，不确定"，待按场景复测（含 §1.4 `--disable-jit-fuser`）。
- **inference 裸 import 阻塞（已由全范围 wheel 关闭）**：`megatron/inference/utils.py` 依赖的 `gpt_builders`/`mamba_builders`/`model_provider` 是 **repo 根顶层入口文件**（不在 `megatron/` 包内）——core-only wheel（0.17.1+flagos）打包时被忽略，安装后 `import megatron.inference.utils` 即 ImportError。MLF PR #107（feat/wheel-full-scope）把顶层入口文件一并打包，hygon 已用该 wheel 验证推理场景跑通（见下）。
  - **归属**：上游 **core_v0.17.0** 自己的代码（fork #34 忠实同步），非 fork 偏离。上游修复时点：0.17.0/0.17.1 = 3 处裸 import；0.18.0/0.18.2 = 2 处；main = 0（全部收敛进 `megatron/training/models/`）。
  - **状态**：全范围 wheel 从打包侧关闭阻塞，其余后端推理列仍 ⛔ —— 需 PR #107 合入后按序验证。结构性问题（决策4 关联："顶层文件作入口"模式不支持 wheel 包发布）仍然成立，但不阻塞交付。
- **hygon inference**：`StaticInferenceEngine(legacy=True)` 路径 E2E 跑通
  （3 请求 × 8 tokens，exit 0）。legacy 静态批处理走 `apply_module(core_attention)`
  （DotProductAttention/sdpa），**不依赖 flash-attn、不编译 triton kernel**——
  对 hygon 属编译器无关路径；推理(F)=⬜ 仅因未在 flagtree 下实测
  （编译器无关，预期可跑）。
- **hygon RL**：全链路 exit 0（vendor triton 3.5.1 + TE 2.10.0 vendor 变体）——
  tokenizer → NCCL 初始化 → TE 模型构建 → dynamic 引擎（cuda graph）→
  text-gen server → 2 训练迭代 → 退出。此前阻塞项已全部关闭：flash_attn
  断言（repack 三处版本串一致 → 2.8.3 满足 ≥2.7.3）、torch 落位 bug
  （repack 剥 torch 依赖）。RL(F)=⬜ 待在 flagtree 下复测。
- **hygon post_training**：driver 跑通（post_training surface 全 import + `simple_generate`，exit 0）。前提是 nvidia-modelopt 已 ad-hoc 装入 runtime venv（`--no-deps`，**未入镜像**——违反"单步安装即可用"目标，modelopt 纳入与否待镜像层决策）。
- **post_training 依赖**：modelopt 是唯一有 vendor 变体的 HARD 依赖（configs.yaml 仅 enflame 有 `enflame-modelopt`）；tqdm 纯 PyPI。NVIDIA 用 NVIDIA modelopt 可用；其余后端成功率不确定。
- **rl 依赖**：模块级仅 pydantic + typing_extensions（纯 PyPI）；全树 0 处 triton/torch.compile，复用 training/core 的编译器链。**注意**：rl 场景阻塞不在依赖面而在推理引擎——dynamic 引擎硬依赖 flash-attn（§5.5；hygon 已由 vendor flash_attn 2.8.3 满足），属场景级缺口，非依赖面缺口。

## 编译器层已知问题（来源 vllm 验证，megatron 需实测——不归并）

- kunlunxin P800 XPU：flagtree 0.6.1+xpu3.6 与 vendor triton 3.0.0 均出现 Triton attention-kernel 编译失败（vllm 侧三处）。
- sunrise：flagtree flash-attn decode hang（vllm 侧），`compiler triton` 规避后 E2E 通过。

## 验证顺序建议

1. **training 场景**：先验双编译器后端（编译器链风险已知存在——hygon 教训），后验单编译器后端。每后端 = runtime 镜像 + wheel 单步安装 + pretrain_gpt.py 小规模跑通。
2. **rl 场景**：依赖面干净，验证成本与 training 相当；同镜像按用途补 pydantic/typing_extensions。
3. **post_training 场景**：仅 NVIDIA 先行，其余后端等 modelopt 可用性结论。
4. **inference 场景**：hygon 已用全范围 wheel（PR #107）验证 ✅（static legacy 路径）；其余后端待 PR 合入后按序验证。
