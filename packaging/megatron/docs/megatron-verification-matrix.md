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

> 注：hygon 的 T 列均按当前 triton **3.5.1** 计——四场景（training/RL/
> post_training/inference）已全部在 3.5.1 下 E2E 复验通过（2026-08-17）。
> 编译器机制跨版本不移植（3.3.0 直出码无 clang 子进程 → 3.5.1 调外部
> clang），3.3.0 时代结论仅作参考。
>
> 注：hygon 的 F 列（2026-08-17 复验后）——flagtree 3.6.0 四场景级 E2E
> 已全验（✅），但 **每场景均需 jit_fuser noop**（§1.4：`--disable-jit-fuser`
> 不足，import 期已绑定 torch.compile，warmup 触发 torch.compile→inductor→
> flagtree `KernelMetadata.cluster_dims` 崩溃；复验用容器侧 jit.py 补丁绕过，
> 上游修复 = 惰性装饰，见 §1.4）。post_training/inference 本身编译器无关。

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
| 海光     | DTK 26.04     | ✅      | ✅      | ✅          | ✅          | ✅        | ✅        | ✅      | ✅      |
| 天数智芯 | COREX 4.4.0   | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 昆仑芯   | XRE 5.37.1    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 沐曦     | MACA 3.7.2.1  | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 沐曦     | MACA 3.8.1.3  | ✅      | ✅      | ⛔          | ⛔          | ✅        | ✅        | ✅      | ✅      |
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

- **metax training（2026-08-18）**：merged wheel
  `0.17.1+fl.20260818.g48b97a13f1bb`（合并 #105/#106/#107/#114），**双编译器
  均 5 iter E2E exit 0**——flagtree 0.6.1（loss 1.084350E+01 → 1.084006E+01）
  与 vendor triton 3.6.0+metax3.8.1.0（loss 1.084290E+01，12:58 run，量级与
  flagtree 线吻合）。环境要点：huggingface.co 不通 → NullTokenizer 离线路径；
  GPU 0 被占用 → `CUDA_VISIBLE_DEVICES=1`。启动命令参数集与 hygon
  相同，**无 jit_fuser noop 补丁前置**（metax flagtree 0.6.1 实测 `--disable-jit-fuser`
  直接够用；hygon 3.6.0 需容器侧 jit.py 补丁，§1.4——编译器机制跨版本不移植）。
- **metax post_training × inference（2026-08-18，双编译器全 ✅）**：两场景均
  编译器无关路径，triton/flagtree 各跑一遍全 exit 0——post_training = DummyModel
  + `simple_generate`（output shape (1,8)，modelopt 0.45.0 ad-hoc 装入，未入
  镜像，同 hygon §1.3.3）；inference = legacy `StaticInferenceEngine` 3 请求 ×
  8 tokens。inference driver 无需外部词表（注入 prompt_tokens + 重写
  detokenize，NullTokenizer 配方自洽），metax 容器无 gpt2 夹具也不阻塞。
- **metax RL（双编译器均 ⛔，阻塞项确认）**：前置 = **MLF local-THD 修复
  （rl_utils.py:666 无条件 thd → 条件构造）** + 无 vendor TE（官网
  maca-transformerengine-3.7.1.0 与 3.8.1.3 形态不匹配，用户定不装，见状态
  #6）——均非 build-infra 可解，待上游/MLF。
- **merged wheel 参数接口重构 = 使用方法变更（2026-08-18 定）**：hygon 验证用
  的全范围 wheel 无此问题，merged wheel 引入 config dataclass +
  `ArgumentGroupFactory` 自动生成参数，`--lr`（`SchedulerConfig`）与
  `--eval-interval`（`TrainingConfig`）默认 `None`——不传即崩：`--lr` → 
  `optimizer_param_scheduler.py:148` `float(None)` TypeError；`--eval-interval`
  → `training.py:3672` `train_iters // None` TypeError。**非功能变更，是使用
  方法变更**：训练功能仍在，但喂参接口重构。影响所有用 merged wheel 的后端，
  **hygon 留下的 E2E 参数基线需逐参数重核**（可能有更多参数同样 None 默认）。
  处置（2026-08-18 定，用法侧规避，不回馈上游）：两参数均随 sync #34
  来自上游 Core 0.17.0（非 fork 偏离，上游 0.17.0 分支已过时，提修复意义
  不大）；`--eval-interval` 默认 None + 无条件除法 = 上游已知缺口，
  `--lr` 属训练必传参数——两者均由复现基线强制传参规避。

- **hygon training**：vendor triton **3.5.1** ✅（2026-08-17 复验：mock data
  5 iter E2E exit 0，loss 1.084036E+01 → 1.083188E+01；3.3.0 时代已验证，但
  编译器机制跨版本不移植，仅作参考）。flagtree 3.6.0 **场景级 E2E 已复验 ✅**
  （2026-08-17，5 iters exit 0，前提 jit_fuser noop，§1.4）。详见
  [[megatron-hygon25-e2e.md]] 与 [[memory/hygon-compiler-mask]]。
- **hygon 编译器版本 × 场景 映射（2026-08-17）**：四场景 E2E 全部在 triton
  **3.5.1** 复验通过（RL：run 13；training/post_training/inference：
  2026-08-17 复验，exit 0）——**编译器机制跨版本不移植**（3.3.0 直出码无
  clang 子进程 → 3.5.1 调外部 clang），3.3.0 时代结论仅作参考。inference
  走 legacy 静态路径，编译器无关（§4）；T 列已逐格回填 ✅。
- **hygon flagtree 场景级状态（2026-08-17 复验完成）**：曾判"屏蔽"系旧容器缺
  DTK LLVM 包所致，已证伪；**四场景 F 列全 ✅**（训练/RL/post_training/inference
  均 exit 0）。跨场景前置：每场景需 jit_fuser noop（§1.4，`--disable-jit-fuser`
  不足——import 期已绑定 torch.compile，warmup 触发 inductor→flagtree
  `cluster_dims` 崩溃；复验用容器侧 jit.py 补丁，上游修复方向 = 惰性装饰）。
  post_training/inference 本身编译器无关（DummyModel / legacy static 路径）。
- **inference 裸 import 阻塞（已由全范围 wheel 关闭）**：`megatron/inference/utils.py` 依赖的 `gpt_builders`/`mamba_builders`/`model_provider` 是 **repo 根顶层入口文件**（不在 `megatron/` 包内）——core-only wheel（0.17.1+flagos）打包时被忽略，安装后 `import megatron.inference.utils` 即 ImportError。MLF PR #107（feat/wheel-full-scope）把顶层入口文件一并打包，hygon 已用该 wheel 验证推理场景跑通（见下）。
  - **归属**：上游 **core_v0.17.0** 自己的代码（fork #34 忠实同步），非 fork 偏离。上游修复时点：0.17.0/0.17.1 = 3 处裸 import；0.18.0/0.18.2 = 2 处；main = 0（全部收敛进 `megatron/training/models/`）。
  - **状态**：全范围 wheel 从打包侧关闭阻塞，其余后端推理列仍 ⛔ —— 需 PR #107 合入后按序验证。结构性问题（决策4 关联："顶层文件作入口"模式不支持 wheel 包发布）仍然成立，但不阻塞交付。
- **hygon inference**：`StaticInferenceEngine(legacy=True)` 路径 E2E 跑通
  （3 请求 × 8 tokens，exit 0）。legacy 静态批处理走 `apply_module(core_attention)`
  （DotProductAttention/sdpa），**不依赖 flash-attn、不编译 triton kernel**——
  对 hygon 属编译器无关路径；**3.5.1 复验通过（2026-08-17，生成 4s，与 3.3.0
  时代 4.2s 吻合）**；flagtree 下复验 ✅（2026-08-17，同 driver，exit 0）。
- **hygon RL**：全链路 exit 0（vendor triton 3.5.1 + TE 2.10.0 vendor 变体）——
  tokenizer → NCCL 初始化 → TE 模型构建 → dynamic 引擎（cuda graph）→
  text-gen server → 2 训练迭代 → 退出。此前阻塞项已全部关闭：flash_attn
  断言（repack 三处版本串一致 → 2.8.3 满足 ≥2.7.3）、torch 落位 bug
  （repack 剥 torch 依赖）。**flagtree 下复验 ✅（2026-08-17，同参数全链
  exit 0，前提 jit_fuser noop，§1.4）**。
- **hygon post_training**：driver 跑通（post_training surface 全 import +
  `simple_generate`，输出 shape=(1, 8)，exit 0）——**3.5.1 复验通过
  （2026-08-17）**；**flagtree 下复验 ✅（2026-08-17，同 driver，exit 0）**。
  前提是 nvidia-modelopt 0.45.0 已 ad-hoc 装入 runtime venv（aliyun 带依赖解析：
  PuLP/antlr4-python3-runtime-4.9.3/nvidia-ml-py/omegaconf/scipy；torch 2.9.0
  落位未动；**未入镜像**——违反"单步安装即可用"目标，modelopt 纳入与否待镜像层决策）。
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
