# Megatron 场景 × 编译器 × 后端 验证矩阵

> 规划工具，随验证推进更新。每单元格为对应后端 runtime 镜像 + 一步安装 wheel 后，对应场景入口跑通的验证。
> wheel 打包范围：core+training+legacy+rl+post_training（inference 因上游裸 import 缺陷挂起，见下）。

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
| 海光     | DTK 26.04     | ✅      | ❌      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
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

- **hygon training**：flagtree 3.6.0 ❌（clang-17 拒 5 个 `-mllvm` flags → 无产物 + 误导性 HSACOError，屏蔽）；vendor triton 3.3.0 ✅（E2E exit 0，loss 9.1295→8.8622）。详见 [[megatron-hygon25-e2e.md]] 与 [[memory/hygon-compiler-mask]]。
- **inference 阻塞（跨团队协调中）**：`megatron/inference/utils.py` 裸 import `gpt_builders`/`mamba_builders`/`model_provider`——这三个模块是 **repo 根顶层入口文件**（gpt_builders.py、mamba_builders.py、model_provider.py，repo checkout 靠 cwd=根 的 sys.path 找到），**不在 `megatron/` 包内**，wheel 打包忽略它们 → 安装模式下 `import megatron.inference.utils` ImportError。此场景不可打包、不可镜像。
  - **归属**：上游 **core_v0.17.0** 自己的代码（fork #34 忠实同步，逐字相同），非 fork 偏离。上游修复时点：0.17.0/0.17.1 = 3 处裸 import；0.18.0/0.18.2 = 2 处（mamba 修了）；main = 0（全部收敛进 `megatron/training/models/`）。
  - **需要 MLF 团队决策**：① resync v0.18.0（代价 = 从 0.17.0 追三代，且 fork 有 22 个 core 文件 cur_platform 替换 + 15 个 FlagScale 专属字段需重放）；② 顶层文件收敛进 megatron 包（~150 行，inference/utils.py 改包内导入，入口脚本不动）。**决定前此场景挂起**。
  - **结构性问题（关联决策4）**：mlf 的"顶层文件作入口"模式本身不支持 wheel 包发布——入口脚本（pretrain_gpt.py 等）与其依赖（gpt_builders.py 等）全在 repo 根，不在 `megatron/` 包内。即便把入口脚本 COPY 进镜像层，其 import 路径仍需包内化。这正是决策②要解决的同一件事。
- **post_training 依赖**：modelopt 是唯一有 vendor 变体的 HARD 依赖（configs.yaml 仅 enflame 有 `enflame-modelopt`）；tqdm 纯 PyPI。NVIDIA 用 NVIDIA modelopt 可用；其余后端成功率不确定。
- **rl 依赖**：模块级仅 pydantic + typing_extensions（纯 PyPI）；全树 0 处 triton/torch.compile，复用 training/core 的编译器链。

## 编译器层已知问题（来源 vllm 验证，megatron 需实测——不归并）

- kunlunxin P800 XPU：flagtree 0.6.1+xpu3.6 与 vendor triton 3.0.0 均出现 Triton attention-kernel 编译失败（vllm 侧三处）。
- sunrise：flagtree flash-attn decode hang（vllm 侧），`compiler triton` 规避后 E2E 通过。

## 验证顺序建议

1. **training 场景**：先验双编译器后端（编译器链风险已知存在——hygon 教训），后验单编译器后端。每后端 = runtime 镜像 + wheel 单步安装 + pretrain_gpt.py 小规模跑通。
2. **rl 场景**：依赖面干净，验证成本与 training 相当；同镜像按用途补 pydantic/typing_extensions。
3. **post_training 场景**：仅 NVIDIA 先行，其余后端等 modelopt 可用性结论。
4. **inference 场景**：挂起，等 MLF 团队决策（resync v0.18.0 / 顶层文件收敛进包）后重新评估。
