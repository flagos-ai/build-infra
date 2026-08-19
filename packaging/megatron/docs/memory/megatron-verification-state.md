---
name: megatron-verification-state
description: megatron 应用镜像验证阶段的状态：已定决策、待决事项、文件状态、任务状态（2026-08-14 结束点）
metadata: 
  node_type: memory
  type: project
  originSessionId: d7f830af-2108-4f39-aba9-825e3ddd911e
  modified: 2026-08-17T09:00:00.000Z
---

# Megatron 应用镜像验证阶段 — 状态快照（2026-08-17 结构决策收口）

**阶段:** hygon25 验证期（build-infra 的 megatron 打包 + 应用镜像工作）。

## 制品结构决策（2026-08-17 全定案，本轮核心产出）

| # | 决策 | 结论 |
|---|---|---|
| D1 | RL 独立 app | **概念属训练**（参数更新主循环），**工程为复合体**（训练+推理引擎+env 服务）→ 不塞进 training 镜像 |
| D2 | training + post_training 一类 | **生产模型用户画像**；post_training 是 modelopt 增量、可后拆 |
| D3 | inference 不独立交付 | **唯一客户是 RL**（`megatron/rl/inference/` text-gen replicas）；独立市场与 vllm 冲突 → 不建 inference 独立 app；inference 是 RL 能力子集 |
| D4 | 命名 | `flagos-app/megatron-training-{vendor}-{backend}` / `flagos-app/megatron-rl-{vendor}-{backend}`，统一 `megatron-` 前缀、对称自明 |
| D5 | 目录组织 | `app/megatron/` 按**上游项目**（Megatron-LM-FL）组织，不拆目录；内含两个 Containerfile（`Containerfile.megatron-training` / `Containerfile.rl`）。切后端=参数化 `-f`，不用分 app 找目录 |
| D6 | TE 归属 | **TE 是 RL app 的 per-application 依赖，不进 runtime**（"太重"）；runtime 定义保持 torch/triton/flag_gems；TE 每后端条件性（hygon 有 vendor TE，其他后端没有）落在 app 层：有 TE 的后端建 RL 镜像，没有的不建——与交付面归并规则咬合 |
| D7 | 镜像拓扑 | **RL 直接 FROM runtime**，不叠加 megatron-training；两 app 并列、互不依赖、层缓存独立，wheel 装两遍无害 |

**镜像形态（最终）:**
```
runtime
├──→ flagos-app/megatron-training-*    = runtime + wheel + modelopt(公共包)
└──→ flagos-app/megatron-rl-*          = runtime + wheel + TE(每后端条件) + RL 13 包组
```

**modelopt 定性：** 公共 PyPI 包（aliyun 装，nvidia-modelopt 0.45.0），非 vendor 包，无每后端条件性 → 声明进 `megatron-training` 的 deps.app 组即可（与 TE 不同，TE 才有条件性）。**安装须测试（2026-08-17 用户定）**：ad-hoc 验证（§1.3.3/§3，torch 2.9.0 落位未动 + import/simple_generate 双编译器过）已证明公共路径可解析；**缺口 = 入镜像单步安装**（megatron-core + modelopt 同一条 pip install，vendor index + aliyun 并列）——测试随 B 走：`pip check` 干净 + torch 落位断言 + §3 driver 复测。

**inference 模块定位：** 不独立交付；活在 RL 镜像（内部引擎）与 wheel 内。megatron app 不含推理服务承诺。

## 阶段二固化待办（2026-08-17 结构决策后刷新）

**B 已定稿（2026-08-17）：两镜像依赖定案。** `megatron-training` = wheel + modelopt + tqdm + datasets(+pyarrow)（post_training 双引用，扫描实证）+ apex(hygon, runtime 继承)；不含 wandb/web 栈/TE（post_training 零引用）。`megatron-rl` = wheel + TE(vendor 条件) + 13 公共包全组 + flash_attn(runtime 继承) + apex(runtime 继承)。**安装两条 RUN**（vendor 装 TE → aliyun 装公共组，index 隔离便于检测）。**flash_attn 结论（2026-08-17 定）**：有则最好、无则有 workaround（MLF 内置一份 / 复用 flag_gems varlen paged——fork vllm-plugin-FL `AttentionFLBackend` 生产模板，vllm_fl/dispatch/backends/flaggems/impl/attention.py:589）。**TE 定性修正**：障碍是代码强制 thd（rl_utils.py:666-682 无条件构造 packed，含 sequence_packing=False 单序列）非 vendor 门；local-THD 修掉后 TE 降为可选加速包。**MLF 两缺口修掉后 RL = 纯公共依赖场景**（假设，待第二后端实证）。**enflame modelopt 例外不担心**（用户：见到了就装，可要可不要）。**verify 定性（用户 2026-08-17）**：断言是测试阶段手段（pip check / torch 落位 / §3 driver / TE+FA 版本断言 / run 13 同款 RL driver），**最终镜像锁定版本后行为即确定**——断言不进最终镜像，锁版才是交付契约。**Containerfile 拆分（#4）已落地：PR #427 OPEN（2026-08-18）**；点 2 lock 版本清单已随 #114 落地（`[rl]` extra 15 包全 pin，含 pyarrow 版本对，§5.2）。

**C 定稿（2026-08-17）："让 wheel 自己说话"。** 公共包依赖真相全部回 MLF extras（`[training]` + `[rl]` 一起提，各带版本 pin，pyarrow 版本对进 datasets 声明）；build-infra 只握顶层 wheel 名 + extra 选择器；configs.yaml `deps_app` 只背 vendor 条件包（TE），**不重复 13 包清单**；两条 RUN（vendor / mirror）保留。**边界规则**：extra 只许公共包；vendor 条件包（TE）不许进 extra，留 deps_app；flash_attn 是 runtime 层继承、不属 app 声明。**MLF pyproject 修 extra 的 PR 升格为 C 前置阻塞项**。C 机制"结构定了、等 MLF PR + hygon RL 验证后落地"。**#1 已提（2026-08-17）：PR #114**（feat/declare-runtime-extras，`[training]` +4 包 pin、新 `[rl]` extra 15 包全 pin）——待合并；C 机制落地解锁条件 = #114 合并。

**C/D 形状（2026-08-17 定稿）：deps_app 每后端显式列全 app（vllm/megatron-training/megatron-rl 一键），vendor 包按需填——`[]` 表示"该 app 在此后端存在、需验证、但无 vendor 包"，不是不建。两职责解耦：app 存在性 = 键本身（验证矩阵全展开依据，期望状态）；vendor 包 = 列表内容（构建时实际装什么）。hygon megatron-rl 有 TE，其余后端全空。交付矩阵（现实状态）是验证结论的产物，不在 configs 硬编码。app 级平级（vllm/training/rl），"rl 是否可建"是每后端待验证项（默认可建）——未来纯公共 RL 后所有后端 rl 皆 `[]` 而恒建。**

1. **`app/megatron/Containerfile` 拆分**（**已落地：PR #427 OPEN，2026-08-18**）：`Containerfile.megatron-training`（wheel + modelopt + tqdm + datasets）/ `Containerfile.rl`（wheel + TE 条件 + 13 包全组）；原 `Containerfile` 改名并留注释说明目录名≠镜像名的对应。**megatron-rl 可建性门槛 = MLF PR #114 合并 + 新 wheel（带 `[rl]` extra）；megatron-training 现 wheel 即可建（`[training]` 已存在）**
2. **configs.yaml `deps_app` 机制**（新建，对称 `env.app`，**已落地：PR #424 OPEN**）：19 后端全展开 `deps_app: {vllm, megatron-training, megatron-rl}`，`[]` = app 存在待验证无 vendor 包（非"不建"）；仅 hygon `megatron-rl` 有 `transformer_engine==2.10.0+das.opt1.dtk2604.torch290`。**wheel 边界（用户 2026-08-17 定案）：wheel 不是 deps_app 条目——是 app 身份，走 Containerfile `MEGATRON_VERSION` arg，判定准则 = 每后端条件性而非装自哪个 index**，已写进 configs.yaml header 注释。公共包（modelopt/tqdm/datasets/13 组）**不在此处**——走 wheel extras（C 定稿，等 #114）
3. **CI 支撑（已落地，两 PR）**：generate_matrix 支持 app 级 deps + `--app {app}` 输出 `app_env`/`app_deps` 随 **PR #424 OPEN**；megatron-app-image.yml 参数化 app 名（`megatron-training`|`megatron-rl` input → 镜像 tag / matrix / APP_DEPS build-arg，Containerfile 前置 vendor RUN）随 **PR #425 OPEN**
4. **apex 纳入 hygon runtime**（A1，2026-08-17 确认，**已落地：PR #422 merged + wheel 已传 flagos-pypi-hygon**）：上传 `apex==1.7.0+das.opt1.dtk2604.torch290` + configs.yaml hygon deps 加 `apex==1.7.0+das.opt1.dtk2604.torch290`。**定性：apex 是 vendor 可选加速包（熔断可选，MLF 里 4 处使用全 try/except fallback——multi_tensor_applier / FusedLayerNorm / FusedAdam），非 RL 硬依赖**；kunlunxin/metax 已有先例（apex==0.1 / apex==0.1+metax3.8.1.0）
5. **TE 每后端条件性登记（已落地，随 #424）**：hygon `megatron-rl` deps_app 登记 `transformer_engine==2.10.0+das.opt1.dtk2604.torch290`；其余后端 `[]`（无 vendor TE，构建时无 vendor 包，RL 纯公共场景假设待第二后端实证）
6. **metax 无 vendor TE（2026-08-18 用户定，2026-08-19 实证坐实非阻塞）**：官网仅有
   `maca-transformerengine-3.7.1.0` 包（TE 2.13.0 + flash_fusion + grouped_gemm
   三件套，wheel 只带 torch2.6/2.8，`.layerspec/` conda 形态，install.sh 按 torch
   X.Y glob 匹配）——SDK/torch/环境形态三样均不匹配 metax 3.8.1.3（torch 2.10.0），
   **官网无 3.8.1.3 版本**。该 3.7.1.0 包或可用于另一后端（maca3.7.2.1 线
   torch2.8），但非关键包，**用户定：不装**。metax `deps_app.megatron-rl` 保持 `[]`。
   **实证（2026-08-19 终止）**：run #17（flagtree 线）完整 GRPO E2E exit 0——
   `--transformer-impl local` 全程无 TE 跑通，**无 vendor TE 确证非阻塞项**。
   **local-THD（rl_utils.py:666 无条件 thd）**：实证链以容器侧条件化补丁
   （transformer_impl=="local" 时 thd=None）落地、非阻塞；归类为 MLF 反馈项
   （见待反馈项），**不再是 metax RL 阻塞项**。真实障碍链 17 个（runs #3–#17）
   全为本地代码/参数/harness 缺陷，详见
   `megatron-verification-matrix.md` metax RL 条目。

**待 MLF 反馈项**（建议权，不阻塞 build-infra）：jit_fuser 惰性装饰、RL extra 声明偏差（**已提 PR #114，见 C 定稿**）、local-THD（rl_utils.py:666 无条件 thd → 条件构造；**2026-08-19 实证：容器侧条件化补丁即通，非阻塞，但 metax RL 走 local impl 必需**）、eos_id None 兜底、dynamic 引擎 flash_attn 依赖软化（megatron.py:87 可配置 fallback）。

## 既有定案（早前，仍有效）

1. **交付形态 = 应用镜像**：wheel 单步安装进 `flagos-runtime-{vendor}-{backend}` 镜像，用户直接跑训练服务。**repo checkout 交付 = 王八蛋方式，不可接受。**
2. **单 wheel，不做多组件**：应用场景归并进一个 wheel（场景是镜像内能力）；镜像种类按本快照 D1-D7 拆分。
3. **编译器归并规则**（用户原话定性）：**验证面不归并**——每个后端 × 两个编译器（flagtree/triton）都要验证；**交付面归并**——每后端只交付能用的编译器，不能用的屏蔽（不设默认/不装）。
4. **hygon 编译器 mask（2026-08-17 修正）**：flagtree 3.6.0 ✅ 可用（四场景复验全过，2026-08-17）——DTK LLVM 前置 + 需 jit.py noop 补丁（§1.4，上游修复未合并）；vendor triton 3.5.1 ✅（repack 后）。详见 [[hygon-compiler-mask]] 与 [[rl-verify-worklog]]。
5. **打包环境 = runtime 镜像**（2026-08-14 用户定）：打包环境 = 交付环境 → 装完 wheel 即可做依赖面安全验证。
6. **repack facility 已删**（2026-08-14）：megatron 是 fork 源码模式，`torch>=2.6.0` 声明保留，repack 无活可干。verify 脚本移至 `packaging/megatron/verify/verify-megatron-backend.sh`。

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
