---
name: rl-verify-worklog
description: RL E2E 验证工作日志——每工作一步记一笔（2026-08-16 用户指定：记录放 packaging/megatron/docs/memory/，不放 agent 个人 memory）
metadata:
  type: project
---

# RL E2E 验证工作日志

## 最终目标（2026-08-16 用户重申）

**可重复构建的、稳定的、可交付的、基于 MLF 的堆栈（镜像）。**

- 一切验证发现最终都要**固化到构建流程**：configs.yaml deps / runtime Containerfile / wheel extras。
- 不在容器内打补丁、不做一次性探索——凡是"构建流程复现不出来"的结论都不算数。
- 当前 RL E2E 验证的产出 = **MLF 堆栈依赖清单**（每个依赖：从哪个 index 来、什么版本、如何声明）。

## 记录方式（2026-08-16 用户定）

- **memory 是现场记录**（用户不看）；用户消费的产物是**最终的、可供借鉴的报告 markdown**。
- 每个验证结论最终都要沉淀成报告（如 packaging/megatron/docs/ 下的报告），memory 只是过程草稿。
- 报告标准：可直接借鉴（结论 + 怎么做 + 坑），不是流水账。
- **所有卡点，只要不是误操作，都要写入 markdown 报告**——技术障碍是报告的核心内容。
- **自己做过的所有探索，都要记入 memory**——探索过程不进报告（报告只留结论），但必须留痕在 memory，可追溯。
- **误操作不入报告，也不留 memory**——做错了 A、后来发现是误操作，没人在意，自己也要尽快忘掉。**删掉无意义的 memory 对保持思路清晰很重要**（定期清理）。
- **容器内可以探索，但探索不等于完工（2026-08-16 用户补充定）**：后面遇到类似的问题（vendor 依赖漏/错等），**都不可以轻易放过**。容器内可以做**所有探索性的修复**，但**修复之后不能在容器里认为完工**——最终落脚点仍然以**可重复的流程、制品**为准（configs.yaml deps / runtime Containerfile / wheel extras / vendor repack）。探索结论必须固化到构建流程才算数。
- **容器内手动补包只允许用于测试目的（2026-08-16 用户定）**：补包的价值 = 暴露"构建流程没声明"的缺口；回过头来每个缺口都要固化到可重复流程。跑不跑通本身不重要。

## 2026-08-16 重开（rl-v4 为新一轮起点）

上一轮（rl-v2/rl-v3）RL 验证记录全部作废，干扰严重，已清除。以 rl-v4 起的新一轮实测为准。

**背景（TE repack 已闭环交付，一句话）：** transformer_engine 2.10.0+das.opt1.dtk2604.torch290 经三项 vendor repack 修正（pandas 补声明 / enable_mmacfuse 剥参 / FA 版本检测剥 local version），从 hygon index 单步安装即完全可用（import + LayerNorm/Linear + DPA thd/fp16 FA 后端均通过）。RL 用 TE 方向已定。

**版本策略（用户 2026-08-16 定）：** 先装最新版本并锁定（pin 死），出问题再说。MLF 已 pin 的（pydantic==2.12.5 / tensorboard==2.19.0）对齐；fastapi 满足 `~=0.50` 取最新 0.x；其余无约束包（tqdm/httpx/uvicorn/datasets/openai[aiohttp]/wandb）装 aliyun 最新稳定版并锁定。将来固化构建流程时以这些锁定版本为准。

**apex（2026-08-16 用户定）：** hygon vendor apex wheel `apex-1.7.0+das.opt1.dtk2604.torch290-cp310-cp310-manylinux_2_28_x86_64.whl`（DTK 26.04 + torch 2.9.0 对齐，与 TE/torch vendor 变体同系）。**要纳入 runtime 镜像**（hygon 构建流程依赖，走 vendor PyPI `flagos-pypi-hygon`，不直接在容器内装——不可重复）。configs.yaml 里 hygon 段当前无 apex 声明（kunlunxin/metax 有）→ 已落地：configs.yaml
hygon deps 加 `apex==1.7.0+das.opt1.dtk2604.torch290` + wheel 上传 `flagos-pypi-hygon`
（build-infra PR #422 MERGED）。

**wheel 自含性（2026-08-17 确认）：** MLF pyproject 的 `py-modules` 把仓库根顶层入口文件打进 wheel：`gpt_builders / mamba_builders / model_provider / pretrain_gpt / pretrain_bert / pretrain_mamba / pretrain_t5 / pretrain_vlm / train_rl`（pyproject.toml:15-25）。wheel 安装后 `python -m pretrain_gpt` / `from gpt_builders import gpt_builder` / `train_rl.py` 直接落在 site-packages（`/flagos/lib/python3.10/site-packages/train_rl.py` 实测在），无需 repo checkout。**但 `examples/` 目录不打进 wheel**——`examples/rl/environments/countdown/`（countdown_agent.py / countdown.py）是仓库测试环境文件，不在 site-packages。跑 countdown agent 需单独拷这两个文件（已拷到容器 /tmp/rl4-countdown/）。

## 2026-08-16 继续（rl-v4 实测记录续）

**版本基准（用户定）：容器内手补包是"胡闹"，降回 MLF pin。** tensorboard/pydantic 已从容器实测版（2.21.0/2.13.4）降回 MLF `rl` extra pin（2.19.0/2.12.5）。→ 将来固化到构建流程时以 MLF pin 为准。

**公共包镜像（用户定）：一律走 aliyun** `pip install -i https://mirrors.aliyun.com/pypi/simple/`，pypi.org 慢；vendor 包仍走 vendor index。已记 agent memory（pip-aliyun-mirror.md）。

**RL 模块 import 链探测**（`from megatron.rl import rl_utils`，逐层暴露）：
- 已装补齐：tqdm（reward_only_agent 需要；pyproject 在 dev/lts extra）
- **缺口 2：httpx** —— `megatron/rl/inference/megatron.py:6` 模块级 import，pyproject 未声明
- **缺口 3：wandb** —— `megatron/rl/rl_utils.py:92` 模块级无条件 `from wandb import wandb_run`；pyproject 仅在**废弃的 mlm extra** 声明 wandb，`rl` extra 没带（缺口 1 tensorboard 的姊妹：模块级硬依赖未声明）
- 其余 RL 第三方依赖一览（对照 pyproject）：openai[aiohttp]、uvicorn、fastapi、datasets（仅 dev extra / 未声明），numpy/yaml/torch.utils.tensorboard 为运行时基础
- **下一步**：装齐剩余公共包（httpx/openai/uvicorn/fastapi/wandb/datasets，aliyun）→ 跑 train_rl.py 完整 import 链

## 2026-08-17 实测：train_rl.py 跑通到 RL 步（rl-v4 容器）

**RL 场景运行形态（架构确认）：**
- 入口 = wheel 内 py-module：`python -m train_rl`（/flagos/lib/python3.10/site-packages/train_rl.py 实测存在）。train_rl.py 自建 MinimalDataset（`pretrain(None, ...)`），**无需 --data-path / --mock-data**。
- **env server 不需要单独起进程**：`get_agent`（rl_utils.py:424）→ `WeightedMultiTask.from_config` **进程内直接实例化 agent**（fastapi_env_server.py 的 `--env-config` standalone 模式是远程部署形态，CI 测试是进程内）。
- **countdown agent 装载方式**：`import_class`（megatron/rl/__init__.py）支持 `.py:` 文件路径形式（`/path/countdown_agent.py:CountdownAgent`，spec_from_file_location，module 名固定 acemath_agent）。**注意：`.py:` 形式是顶层 module → countdown_agent.py 里的 `from .countdown import compute_score` 相对导入会炸**，需 sed 改绝对导入 `from countdown import compute_score` + PYTHONPATH 指到文件目录（容器内已改）。
- **countdown dataset**：CountdownAgent.get_dataset 断言 `len(dataset) > TRAIN_SIZE(327680)+TEST_SIZE(1024)` → 之前 save_to_disk 的 4096 行不够，已重新 save_to_disk 全量 490364 行（HF cache 命中，秒级）到 /tmp/rl-env/countdown-tasks-3to4（覆盖旧损坏目录，旧的 state.json 是 lock 残留会炸 arrow 读取）。
- **tokenizer**：gpt2 经代理下载到 /tmp/rl-env/gpt2-tokenizer（tokenizer.json/vocab.json/merges.txt 等 4 文件），HF cache 里只有部分文件（只有 vocab.json），snapshot_download 补全。
- 容器内准备文件：/tmp/rl4-countdown/{countdown_agent.py,countdown.py}、/tmp/rl4-env-config.yaml（`.py:` 形式 + dataset_file=/tmp/rl-env/countdown-tasks-3to4 + split=train）、/tmp/run.sh（train_rl 命令）。

**train_rl.py 命令要点（2026-08-17 实测构造）：**
- 模型极小化：--num-layers 2 --hidden-size 64 --ffn-hidden-size 256 --num-attention-heads 4 --seq-length 128 --inference-max-seq-length 64
- CI 借参数：--perform-rl-step --grpo-group-size 2 --grpo-prompts-per-step 2 --grpo-iterations 1 --grpo-clamp-eps-lower/upper 0.2/0.2 --grpo-kl-beta 0.0 --grpo-entropy-term-weight 0.0 --langrl-env-config --rl-partial-rollouts --refit-method gloo --rl-inference-tensor-model-parallel-size 1 --rl-inference-pipeline-model-parallel-size 1 --inference-dynamic-batching-num-cuda-graphs 1 --inference-dynamic-batching-buffer-size-gb 20 --calculate-per-token-loss --untie-embeddings-and-output-weights
- DCU 基线：--no-masked-softmax-fusion --attention-backend unfused --transformer-impl local --bf16
- 未用 CI 的 --finetune/--use-checkpoint-args（无 ckpt 加载）
- 结果日志 /tmp/rl4-train.log（容器内）

## 2026-08-17 第三轮启动：两个新阻塞 + 跑到 NCCL init

**阻塞 D（transformers，真实缺口）：** `HuggingFaceTokenizer` 路径 `AutoTokenizer.from_pretrained` 抛 NameError（`AutoTokenizer` 未定义）→ 容器无 transformers。pyproject 里 transformers 只在 **training extra**（pyproject.toml:91），`rl` extra 没带 → 真实缺口。另有代码缺陷：`huggingface_tokenizer.py` 模块级 `HAVE_TRANSFORMERS` 标志算了但从未使用 → 报错是 NameError 而非干净的提示。容器内 aliyun 补装 transformers 5.15.0 + tokenizers 0.22.2（仅测试用途）。依赖已收进 `[rl]` extra（MLF PR #114，OPEN）。

**阻塞 E（python3-config，已知问题 §2.4 在 rl-v4 复现）：** `megatron/training/initialize.py:191 _compile_dependencies → core/datasets/utils.py:30 compile_helpers()` `subprocess.check_output(["python3-config","--extension-suffix"])` → FileNotFoundError。venv `/flagos/bin` 缺 python3-config。**关键确认：wheel 内 `helpers_cpp.cpython-310-x86_64-linux-gnu.so` 已存在**（编译扩展自带），所以补上 python3-config 后 compile_helpers 会提前 return 跳过 make——symlink 即完全解锁。诊断软链（仅测试用途）：`ln -sf /root/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/bin/python3-config /flagos/bin/python3-config`，`--extension-suffix` 实测输出与 wheel 内 .so 同名。**固化路径已生效：** build-infra builder 的 `patch-compile-helpers-sysconfig.py`（sysconfig 替代 python3-config，PR #112 同款）已随 merged wheel（0.17.1+fl.20260818）重建打上，此阻塞消失。

**第三轮启动（含 MASTER_ADDR 四 env + python3-config symlink）进度：** tokenizer 初始化通过（padded vocab 50257→50304）→ RerunStateMachine → TP=1/PP=1 initialized → NCCL ProcessGroup init（W0816 Guessing device ID...）。下一步看：模型构建 → env agent 装载 → §5.1 flash-attn 断言。

## 2026-08-17 第四轮：阻塞 F（max_tokens >= max_requests 断言，参数组合问题）

**阻塞 F（dynamic_context 断言，非依赖缺口）：** 第三轮跑到 RL rollout 数据准备即崩：`megatron/core/inference/contexts/dynamic_context.py:527-530` `assert max_tokens >= max_requests`（"to have consistency between cuda graph sizes and the block table size"）。

- **max_tokens=16384 = DEFAULT_MAX_TOKENS**（dynamic_context.py:236/524：`inference_config.max_tokens or DEFAULT_MAX_TOKENS`）——run.sh 没传 `--inference-dynamic-batching-max-tokens`。
- **max_requests=163836 = KV block 数派生的上限**（508 行 `kv_block_allocator.total_count - 1`，再 `//tp_size*tp_size`、`//4*4` 取整）：20GB buffer（`--inference-dynamic-batching-buffer-size-gb 20`）÷ 极小模型每 block 字节（2 层 hidden 64，block_size_tokens=256）→ ~16.3 万个 block。模型越小 block 越多，断言越容易炸——CI 用 36 层 qwen3-8b + seq 1024，每 block 大得多，不炸。
- **阻塞链**：MASTER_ADDR ✅ → python3-config ✅（诊断 symlink）→ transformers ✅（真实缺口）→ NCCL ✅ → flash-attn 版本断言 ✅（repack 的 __version__ 修正生效，§3.1.1）→ **⛔ F 此处**。
- **处置（参数组合，CLI 可解）：** run.sh 显式加 `--inference-dynamic-batching-max-tokens 262144`（覆盖 DEFAULT_MAX_TOKENS，高于 max_requests 163836）。不动 buffer/block 计算，只抬高 max_tokens 上限。另一个等价选择是 `--inference-dynamic-batching-max-requests` 压到 16384 以下或调小 buffer，未取。

**路径确认（为挑 fix 读的代码，不留报告）：** `rl_utils.py:1577 get_grpo_data_iterator → get_environment_rollouts(model, inference_model, optimizer, grpo_prompts_per_step=2, grpo_group_size)` → DynamicInferenceContext.__init__。CLI override 从 `megatron/inference/utils.py:340-341` 进 InferenceConfig（`--inference-dynamic-batching-max-requests` arguments.py:1869 / `--inference-dynamic-batching-max-tokens` arguments.py:1874，均默认 None）。`get_rollout_generator`（rl_utils.py:458-477）per-request `max_tokens = args.inference_max_seq_length`（=64，是每请求生成长度，与 context max_tokens 无关）。`rl_parallel_generation_tasks` 默认 512（arguments.py:463 else 分支，与 CI 相同）。

## 2026-08-17 第四轮实测续：阻塞 G（pyzmq + msgpack，真实缺口 ×2）

**max_tokens override 生效**：DynamicInferenceContext 正常分配（active buffer 20 GB / 163839 blocks），断言 F 通过。模型构建、env agent 装载、rollout 收集全部走到。

**阻塞 G（InferenceCoordinator 硬依赖 pyzmq + msgpack，均未声明）：** rollout 启动即崩：
- `megatron/rl/inference/megatron.py:100 launch → dynamic_engine.py:477 start_listening_to_data_parallel_coordinator`：`assert HAVE_ZMQ`（dynamic_engine.py:76-80 try/except import zmq 置标志）→ `AssertionError: please install the pyzmq library to use InferenceCoordinator`。
- 同函数 481 行紧接着 `assert HAVE_MSGPACK`（messagepack）——**msgpack 也是同一路径的硬依赖**，装完 pyzmq 必踩。
- **pyproject 声明检查：pyzmq、msgpack 均无**（本地仓库 pyproject.toml grep 0 命中）→ 真实缺口，与 tensorboard/httpx/wandb 同类。
- 容器内 aliyun 补装（仅测试用途）：pyzmq 27.1.0、msgpack 1.2.1。版本未 pin——将来固化到构建流程时以 aliyun 最新稳定版为准（或 MLF rl extra 声明）。
- **固化**：报告 §5.5 依赖表已补 pyzmq/msgpack 两行；依赖已收进 `[rl]` extra（MLF PR #114，OPEN）。

## 2026-08-17 收尾：阻塞 H（arrow 往返）与 I（quart）双破

**阻塞 H（datasets/pyarrow 版本兼容缺陷，非数据损坏）：** `load_dataset("arrow")` 读 datasets 5.0.1 `save_to_disk` 产物报 `ArrowInvalid: Expected to read 538970747 metadata bytes, but only read 243` → 回退 `pa.ipc.open_file` 报 `Not an Arrow file` → DatasetGenerationError。

- **根因（probe 四探证实）**：datasets 5.0.1 save_to_disk 写的 IPC stream 尾部带**零长消息终止符** `ff ff ff ff 00 00 00 00`（continuation + 0 长度），pyarrow 25.0.1 的 stream 迭代（arrow builder 逐批读）把它误读为 538970747 字节长度前缀。**不是文件截断/损坏**——3 行 800 字节小文件同样复现，大文件头部（continuation + 432B schema）与数据段（19.7MB）结构完全正常。
- **probe 四探结果**：① 独立 `pa.ipc.open_stream` 构造成功（lazy，未迭代时误导）但 open_file FAIL；② `pa.ipc.new_file`（ARROW1 footer 格式）产物 → load_dataset OK；③ `pa.ipc.new_stream`（纯流，无零长终止符）产物 → load_dataset OK；④ datasets 自身 save_to_disk → load_dataset FAIL。
- **pyarrow 降级尝试无效**：aliyun 无 21.0.2，装 21.0.0 后 probe ④ 仍 FAIL（同版本写+读也挂）→ 不是写/读版本错配，是 datasets 5.0.1 writer 与 arrow builder reader 的配对缺陷。
- **处置（测试用途，已生效）**：不再用 save_to_disk，改用 `pa.ipc.new_stream` 手工写 `data-00000-of-00001.arrow`（probe ③ 验证可读），全量 490364 行重写到 /tmp/rl-env/countdown-tasks-3to4，`load_dataset("arrow")` 验证 OK（sample {'target': 98, 'nums': [44, 19, 35]}）。
- **对构建流程的意义**：pyarrow 不在 configs.yaml 治理面（datasets 的传递依赖）；但 MLF CI 的 artifact 生成（tests 里 `dataset_file: /mnt/artifacts/...` 预生成）若用同一套 datasets 5.0.1 + pyarrow ≤25 组合会踩同坑 → 报告 §5.5 记一条，建议 CI 固定经过实测的 (datasets, pyarrow) 组合。

**阻塞 I（quart + hypercorn，真实缺口 ×2）：** rollout 起 text-gen replicas 时 4× `RuntimeError: Web backend framework (Quart) not available`（text_generation_server.py:58）。

- pyproject 声明检查：quart（pyproject.toml:132）、hypercorn（:130）均在 **dev extra**，`rl` extra 没带 → 与 transformers（training extra）同类，"声明错位"变体（声明了但挂在别的 extra）。
- 容器内 aliyun 补装（仅测试用途）：quart + hypercorn，`from quart import Quart` OK。
- **固化**：报告 §5.5 依赖表已补 quart/hypercorn 两行；依赖已收进 `[rl]` extra（MLF PR #114，OPEN）。

## 2026-08-17 第六轮：阻塞 K（rollout 长度断言，参数组合问题）

**阻塞 K（非依赖缺口）：** run 8（J 修复后）rollout 收集成功但 GRPO 数据准备即崩——`rl_utils.py:791` `assert (len(turn_traj) == seq_len) or (turn_traj[-1] == tokenizer.eod)`，`AssertionError: Rollout is not the correct length: 112 6763`（112=实际长度，6763=末 token id，非 EOD）。

- **根因**：无 ckpt 随机初始化模型生成的是胡话，**几乎不吐 EOD**；rollout 长度只能靠引擎截断凑。run 8 `--inference-max-seq-length 112 < --seq-length 128` → 引擎 112 处截断 → `len(turn_traj)=112 ≠ 128` 且末 token 非 EOD → 断言两条件全不满足。
- **CI 对照**：CI grpo 全部 `--seq-length == --inference-max-seq-length`（1024=1024），且模型是训练过的会正常吐 EOD——CI 从不触发这条断言，是 CI 没覆盖的边界。
- **处置**：`--inference-max-seq-length 128`（= seq-length）。**结论写进报告基线：无 ckpt 随机初始化 + 无 EOD 的 rollout，inference-max-seq-length 必须 == seq-length**（引擎截断成为唯一长度来源）。
- 阻塞 K 与 F/J 同类（参数组合），非依赖缺口。run 9 已带修复重跑。

## 2026-08-17 第五轮：阻塞 J（inference-max-seq-length 小于 prompt 长度，参数组合问题）

**阻塞 J（非依赖缺口）：** run 7（H/I 双破后首个完整 rollout）在 `Collecting rollouts, Iteration 0` 即崩——text-gen 4 replicas 全部 `MaxSequenceLengthOverflowError`，`Prompt Tokens: 86 / Tokens to generate: -22 / Max sequence length: 64`。dynamic 引擎拒绝全部请求（dynamic_engine.py:823 每请求一个 UserWarning），rollout gather 全失败后 server 关闭。

- **根因**：per-request `max_tokens = args.inference_max_seq_length`（=64，run.sh 沿用 CI 的推理最大生成长度），countdown prompt 本身 84–86 tokens > 64 → `tokens_to_generate = max_seq_length - prompt_tokens` 为负数 → 引擎拒绝。**与阻塞 F 同类（参数组合），非依赖缺口。**
- **CI 对照**：`gpt_grpo_basic_function/model_config.yaml` 用 `--seq-length 1024 --inference-max-seq-length 1024`（两者相等，8b 模型 prompt 短得多）。本 recipe 2 层小模型 seq-length 128，prompt 反而长（countdown 数字序列）。
- **处置**：`--inference-max-seq-length 64 → 112`（>86 prompt + ~26 生成余量），run 8 已带修复重跑。教训写进报告可复现参数基线：**小模型 + 长 prompt 环境（countdown）时 inference-max-seq-length 必须 ≥ prompt 长度 + 期望生成长度**。

## 2026-08-16 新一轮实测记录（rl-v4）

- megatron wheel `0.17.1+fl.20260814.gba22f6b673f3` 已在 rl-v4（hygon index 上有 3 个 cp310 wheel）。
- **缺口 1：tensorboard** —— `megatron/rl/rl_utils.py:24` 模块级 `from torch.utils.tensorboard import SummaryWriter`，wheel METADATA 未声明 → 单步安装后 RL 入口 import 期阻塞（报告 §5.4 已记，性质同 §1.2 psutil）。
- MLF 分支 `feat/rl-optdeps-verify` HEAD `3824c85b8` 已在 pyproject.toml 声明 `rl` extra：`pydantic==2.12.5` + `tensorboard==2.19.0`；**但未合入 main → 无 wheel 可装**（CI 从 main 构建）。
- **对 MLF 只有建议权，没有决定权**（用户 2026-08-16 定）：推进主动权在 build-infra 侧——依赖面在**我们自己的构建栈**声明（runtime configs.yaml deps / wheel 构建流程），不依赖 MLF 合入；MLF 侧 PR 保持开放供采纳。

## 2026-08-17 第七轮（run 10）：阻塞 L 已解，新阻塞 M（gpt2 无 EOD 元数据）

**阻塞 L（参数组合，已解）：** `prepare_trajectories`（rl_utils.py:1055-1071）`ValueError("No pad token found in tokenizer vocabulary")` —— gpt2 vocab（50257）里没有 `<|finetune_right_pad_id|>` / `<SPECIAL_999>`（DEFAULT_PAD_TOKENS 全缺），且 HF pad_token/eos_token/bos_token 全 None。

- **CLI 解法（已生效）**：run.sh 加 `--tokenizer-special-tokens '<|finetune_right_pad_id|>'` → `build_tokenizer` 经 `additional_special_tokens` 把 token 加进 vocab（实测 50257→50258）→ prepare_trajectories 的 vocab 检查命中 → `tokenizer._tokenizer.pad_token = pad_token` 设置成功。**注意 shell 必须加引号**（`<|...|>` 含管道符，裸写会 syntax error）。
- **性质**：参数组合问题，非依赖缺口。但对 MLF 是代码级发现：prepare_trajectories 对无 pad tokenizer 无兜底（直接 raise）。

**阻塞 M（当前，未解）：** pad 设置成功后崩在 **log 语句**：rl_utils.py:1085 `tokenizer.detokenize([tokenizer.eod])` → gpt2 无 eos_token → `eod` property 返回 None（huggingface_tokenizer.py:315-320）→ `ids_to_text([None])` → transformers `convert_ids_to_tokens` `TypeError: int() argument must be ... not 'NoneType'`。

- **根因链**：gpt2 tokenizer 三缺（pad/eos/bos 全 None）→ pad 补上了，EOD 没补 → prepare_trajectories 的 debug 日志（1080-1086 行 PAD/EOD 各一条 detokenize）直接炸。
- **明天方向（未动手）**：
  - 方案 a（推荐，参数层）：tokenizer 换带 eos 的（qwen 系），或经 `--tokenizer-special-tokens` 同时补 `<|endoftext|>` 做 eos？——**注意**：`additional_special_tokens` 加的是特殊 token，HF eos_token 属性仍是 None，`eod` property 仍返回 None，光加 vocab 不够；需要确认是否有 CLI 路径能设 eos_token（`--tokenizer-...` 参数面，build_tokenizer 未传 eos_token，见下）。
  - 方案 b（代码层，记录给 MLF）：`detokenize`/`eod` 对 None 的兜底；或 prepare_trajectories 日志判 None。容器内只做测试性验证，结论固化到报告/PR。
- **代码确认（本地仓库）**：huggingface_tokenizer.py `eod` property（315 行）`if eos_token is None: return None`；`eos_id`（310 行）无 None 检查直接 `tokens_to_ids([None])`（更脆）。build_tokenizer.py 不传 eos_token 给 HF 包装类。
- **日志位置**：/tmp/rl4-train.log 4251-4261 行。run 10 进程已退出（ran out，无残留）。

## 2026-08-17 第八轮（run 11-13）：阻塞 M 数据层解 + 阻塞 N（TE 必需）→ **RL E2E 全链路首次跑通（run 13, exit 0）**

**阻塞 M（已解，纯数据层，无 megatron core 改动）：** 用户质疑"改 megatron core 思路不对" → 重读代码发现包装类 `HuggingFaceTokenizer.add_special_tokens` 有**拷贝回环**（huggingface_tokenizer.py:208-209：`for k in self.tokenizer.SPECIAL_TOKENS_ATTRIBUTES: setattr(self, k, getattr(self.tokenizer, k, None))`，在 __init__ 末尾执行）→ `self.eos_token = eos_token`（None kwarg）会被底层 HF tokenizer 的 eos_token 覆盖。**因此只需数据层修复：** tokenizer_config.json 声明 `bos_token/eos_token/unk_token = "<|endoftext|>"`（容器 /tmp/rl-env/gpt2-tokenizer/tokenizer_config.json，仅测试用途）→ HF AutoTokenizer 报 eos → 拷贝回环传播到包装类。

- **容器内验证（rl4-tokcheck.py）**：`type: GPTTokenizer / HuggingFaceTokenizer`，`inner eos_token: '<|endoftext|>'`，`inner eos_id: 50256`，`tok.eod: 50256`，`tok.eos_id: 50256`，`tok.pad_id: None`，`tok.bos_id: 50256`，`vocab_size: 50258`（pad 已加入），`eod detokenize: '<|endoftext|>'`。✅
- **run 11 实测确认**：日志 2185-2186 行 `Tokenizer PAD: '<|finetune_right_pad_id|> (50257)'` / `Tokenizer EOD: '<|endoftext|> (50256)'` —— 正是 run 10 崩溃点（rl_utils.py:1085 detokenize），完全通过。**未改任何 megatron core 代码。** 用户判断正确。
- **固化的意义**：这是**数据集/tokenizer 配方要求**——gpt2 系（无 eos 元数据）需 tokenizer_config.json 声明 eos/bos/unk；qwen3 系天然带 eos，无需处理（CI 永不踩 M）。
- **代码级发现（降级为 minor，供 MLF）**：`eos_id`（huggingface_tokenizer.py:310-312）无 None 检查直接 `tokens_to_ids([None])`（比 eod 更脆）；build_tokenizer.py 不传 eos/bos/pad kwarg（包装类靠拷贝回环自愈）。

**阻塞 N（参数组合，已解）：** run 11 过 M 后崩在 GRPO 数据准备：`dot_product_attention.py:158 AssertionError: Packed sequence is not supported by DotProductAttention. Please use TEDotProductAttention instead.`

- **根因**：`get_logprobs`（rl_utils.py:666-679）为 CUDA graph signature 一致**无条件构造 thd 格式 packed_seq_params**（sequence_packing=False 时也构造单序列 thd），传给 model → **local impl 的 DotProductAttention 断言炸**。RL 训练 forward 强制 thd packed → 只有 `TEDotProductAttention`（TE）支持。
- **run.sh 参数错误**：`--transformer-impl te` 非法（choices: local/transformer_engine/inference_optimized）→ run 12 参数解析即退。
- **处置（已生效，run 13）**：`--transformer-impl transformer_engine` + 去掉 `--attention-backend unfused`（local 时代 DCU 基线，TE 线不需要）。TE 2.10.0+das.opt1.dtk2604.torch290 import 验证 OK（container 内 `import transformer_engine as te`）。
- **CI 对照**：CI qwen3-8b 不传 transformer-impl → 默认 transformer_engine → 天然不炸；CI 从没覆盖 local impl 的 RL 训练 forward。**结论：RL 训练 forward 必须 TE，local 走不通——与"RL 用 TE 方向已定"一致。**
- **平台依赖警示（用户 2026-08-17 强调）**：TE 不安装跑不起来是**另一个问题**，要记下来——**并不是所有后端都有厂商提供的 TE**。hygon 有 vendor TE repack（已闭环交付），但其他无 vendor TE 的平台走 RL 训练 forward 会卡在这里（要么 MLF 支持 local 的 thd packed，要么平台自建 TE）。

**run 13 = RL E2E 全链路首次跑通（exit 0）：** tokenizer 初始化 → NCCL → 模型构建（TE）→ env agent 装载 → rollout 收集 → prepare_trajectories（PAD/EOD 日志正常）→ **compute_logprobs_batch TE forward 训练（run 11 崩溃点）** → 2 次训练迭代 → `[exiting program at iteration 2]`，0 Traceback，text-gen 前端干净关闭（"Inference Coordinator: shut down successfully"）。日志 /tmp/rl4-train.log（2026-08-17 11:34-11:36）。**RL 场景在 hygon 全链可跑。**

**补充复核（flash-attn 断言实证通过）：** run 13 过后对 §5.1 的动态引擎 flash-attn 断言做容器内实测——`flash_attn.__version__` = `"2.8.3"`（`__init__.py` 首行），`get_fa_version()` = 2.8.3 ≥ 2.7.3 → `is_fa_min_version("2.7.3")` = True，`HAVE_FA3` = False（无 flash_attn_3/flashattn_hopper）但 or 分支满足。**§5.1 上文记的"__version__ 硬编码 2.6.1"来自更早容器/轮子状态，在当前已验证容器不成立（已实证 2.8.3）**。报告 §5.1/§5.6 已按此修正：动态引擎 flash-attn 断言不再是 RL 阻塞，阻塞链止于 TE 要求。

## 2026-08-17 3.5.1 复验（用户批准计划：Triton 升级后 RL 之外场景全测）

**training(T) 复验 ✅（run: pretrain35，vendor triton 3.5.1）：** `compiler triton` 下
`python -m pretrain_gpt`（wheel 内 py-module，full-scope wheel 0.17.1+fl.20260814）mock
data 5 iter 全跑完 exit 0。loss 1.084036E+01 → 1.083188E+01（5 iter，lr 1e-6 constant
下降极小符合预期；3.3.0 时代 loss 9.1295→8.8622 因当时参数/初始化不同，不直接可比）。
参数 = §2 DCU 基线（--no-masked-softmax-fusion --disable-jit-fuser
--no-persist-layer-norm --no-gradient-accumulation-fusion --attention-backend unfused
--transformer-impl local --bf16）+ --untie-embeddings-and-output-weights + seed 42。
NCCL 正常拆解退出，0 Traceback。**3.5.1 下 training E2E 跑通。**

**post_training(T) 复验 ✅（run: posttrain35，vendor triton 3.5.1）：** `compiler triton`
下 `/tmp/posttrain35.py` driver（post_training surface 全 import + `simple_generate`）
exit 0，输出 shape=(1, 8)——与 3.3.0 时代事实逐字一致。modelopt 依赖链走通：
checkpointing.py:7 模块级 import modelopt.torch 由 ad-hoc 装入的 nvidia-modelopt
0.45.0（aliyun，带依赖解析：PuLP/antlr4-python3-runtime-4.9.3/nvidia-ml-py/
omegaconf/scipy；torch 2.9.0 落位未动）满足——**测试用途，未入镜像**（§1.3.3
决策未变）。simple_generate 走 forward_backward_no_pipelining，DummyModel 需满足
MegatronModule 最小接口（config/set_input_tensor/model_type）。MASTER_PORT=29502。

**inference(T) 复验 ✅（run: infer35，vendor triton 3.5.1）：** `compiler triton` 下
`/tmp/infer35.py` driver（legacy static 引擎）exit 0，3 请求 × 8 tokens，生成耗时
4s（tqdm 3/3 [00:04, 1.49s/it]）——与 3.3.0 时代"generate 4.2s"吻合。**编译器无关
路径成立**：StaticInferenceContext → is_static_batching() → attention.py static 分支
apply_module(core_attention)（DotProductAttention/sdpa），不依赖 flash-attn、不编译
triton kernel。两处 driver 内 bypass（测试用途）：prompt_tokens 直接注入
InferenceRequest 绕过 NullTokenizer 无 tokenize()；NullTokenizer 补最小 detokenize
（controller.detokenize 无条件 inspect.signature，text_generation_controller.py:209）。
模型 = 与 training 同构 gpt_builder 随机初始化（无 ckpt），3 个 InferenceRequest
request_id=0/1/2 + sampling_params(num_tokens_to_generate=8)。MASTER_PORT=29503。

**3.5.1 复验总结：** 三场景（training/post_training/inference）在 vendor triton
3.5.1 下全部 exit 0——升级后仅 RL 复验（run 13）的缺口已补全。T 列逐格回填 ✅
（矩阵 2026-08-17）。

## 2026-08-17 第九轮：FlagTree 四场景复验（用户指令"hygon 上的 FlagTree 从头验一遍"）

**范围：** `compiler flagtree`（3.6.0）下四场景全验——training / RL / post_training / inference（矩阵 F 列原为 ⬜）。

**核心发现（§1.4 实证）：`--disable-jit-fuser` 不足。**
- `enable_jit_fuser()` 在模块 import 期把 `jit_fuser` 绑定为 `torch.compile`（megatron/core/jit.py:16-33）；`--disable-jit-fuser` 在 args 解析后才翻转，**晚于装饰器生效点**。args dump 里 `--disable-jit-fuser` 已是 True，warmup（initialize.py:495 `_warmup_jit_function`）**仍执行 torch.compile** → torchinductor → flagtree 3.6.0 内核缺 `cluster_dims` 元数据 → `AttributeError: 'KernelMetadata' object has no attribute 'cluster_dims'`（torch 2.9.0 `triton_heuristics.py:1757 make_launcher`）。
- **测试绕过（容器内，非仓库改动）：** site-packages `megatron/core/jit.py` 末行 `enable_jit_fuser()` → `disable_jit_fuser()`（备份 /tmp/jit.py.bak）。上游修复方向 = 惰性装饰（§1.4 已建议，已上提：MLF #121 issue → PR #122，OPEN）。
- **影响面：** training 与 RL 均触发 warmup torch.compile；post_training/inference 的 driver 不走 warmup（编译器无关路径）——但 RL 场景若不用补丁，与 training 同样在 warmup 崩。

**四场景结果（均 `compiler flagtree`，日志 /tmp/flagtree-*.log）：**
- **training ✅**（flagtree-training2.log）：`pretrain_gpt.py` 5 iters，loss 1.0838E+01 → 1.0835E+01，EXIT=0。首次失败（training1）即 `cluster_dims` 崩溃，补丁后通过。
- **RL ✅**（flagtree-rl.log）：同 run 13 参数（TE 线），全链 exit 0——rollout → logprob → 2 训练迭代 → "Inference Coordinator: shut down successfully"。TE triton kernel 在 flagtree 3.6.0 下编译正常。
- **post_training ✅**（flagtree-posttrain3.log）：DummyModel + `simple_generate`（1,8），EXIT=0。编译器无关路径。前两次失败为 wrapper 缺 args（assert micro_batch_size）与 MASTER_ADDR——脚本问题，非场景问题。
- **inference ✅**（flagtree-infer2.log）：`StaticInferenceEngine(legacy=True)` 3 请求 × 8 tokens，EXIT=0。编译器无关路径（不编译 triton kernel）。

**文档产物：** 矩阵 hygon 行 F 列全 ✅ + 顶部注更新；报告 §0（flagtree 线小节）、§1.4（实证结论）、§2 基线表、§3/§4/§5（各场景 flagtree 复验注）、§6（待决策项关闭）。

## 待办/开放问题

- [x] **阻塞 M 已解（2026-08-17，run 11 确认）**：数据层修复（tokenizer_config.json 声明 eos/bos/unk）+ 包装类拷贝回环（huggingface_tokenizer.py:208-209）→ eod=50256 正常。gpt2 系 tokenizer 配方要求写进报告；`eos_id` 无 None 兜底是 MLF minor 发现。**已关闭**
- [x] **阻塞 N 已解（2026-08-17，run 13 确认）**：RL 训练 forward 强制 thd packed → **必须 `--transformer-impl transformer_engine`**，local 走不通；`--attention-backend unfused` 移除。**平台依赖警示（用户定）：不是所有后端都有厂商 TE** —— 无 vendor TE 平台需 MLF 支持 local 的 thd packed 或平台自建 TE，写入报告。**已关闭**。local-THD 条件化已上提（MLF PR #116，OPEN）；metax 无 vendor TE 双编译器实证非阻塞（2026-08-19）
- [x] **阻塞 L 已解记录**：`--tokenizer-special-tokens '<|finetune_right_pad_id|>'`（必加引号）是 gpt2 无 pad 场景的 CLI 解法；prepare_trajectories 无 pad 兜底是 MLF 代码发现（rl_utils.py:1055-1071）
- [x] **quart + hypercorn 缺口固化**（2026-08-17 实测，阻塞 I）：text_generation_server.py:58 硬依赖 quart，pyproject 声明在 dev extra（pyproject.toml:132/130），`rl` extra 没带 → **已收进 `[rl]` extra（MLF PR #114，OPEN）**
- [x] **datasets/pyarrow 组合验证**（2026-08-17 实测，阻塞 H）：datasets 5.0.1 save_to_disk → load_dataset("arrow") 往返在 pyarrow ≤25 下损坏（零长终止符误读）；容器内已用 pa.ipc.new_stream 手工重写绕过。**实测版本对已固化进 MLF pyproject datasets 声明（#114 内）**
- [x] **transformers 缺口固化**（2026-08-17 实测）：HuggingFaceTokenizer 需要 transformers，pyproject 仅 training extra 有，`rl` extra 没带（pyproject.toml:91）→ **已收进 `[rl]` extra（MLF PR #114，OPEN）**；另有代码缺陷 HAVE_TRANSFORMERS 未使用（huggingface_tokenizer.py）
- [x] **pyzmq + msgpack 缺口固化**（2026-08-17 实测，阻塞 G）：InferenceCoordinator 路径硬依赖（dynamic_engine.py:477/481），pyproject 均未声明 → **已收进 `[rl]` extra（MLF PR #114，OPEN）**
- [x] **python3-config 已固化**：builder 的 patch-compile-helpers-sysconfig.py 已就位（PR #112 同款）；merged wheel（0.17.1+fl.20260818）已带该补丁，单步安装后此阻塞消失
- [x] **apex 纳入 hygon runtime 镜像**（用户定）：已落地——wheel 上传 `flagos-pypi-hygon` + configs.yaml hygon deps 加 `apex==1.7.0+das.opt1.dtk2604.torch290`（build-infra PR #422 MERGED）
- [x] tensorboard 缺口固化：**已收进 `[rl]` extra（MLF PR #114，pin 2.19.0 对齐）**
- [x] RL 完整接入 TE 实测：hygon TE 线全链 exit 0（run 13，2026-08-17）；metax 无 vendor TE 走 local（#116）+ 双编译器实证非阻塞（2026-08-19）；ascend RL 暂停（动态引擎 flash_attn 依赖，见矩阵）
- [x] MLF 侧 PR：**#114 OPEN**（feat/rl-optdeps-verify 的 `[rl]` extra 全量 pin + datasets 版本对）
- [x] **jit_fuser 惰性装饰修复反馈 MLF（2026-08-17 flagtree 复验实证，§1.4）**：
  `--disable-jit-fuser` 不足（import 期绑定早于 flag 翻转），flagtree 线 warmup
  必崩 `cluster_dims`；容器 rl-v4 有测试用 jit.py 补丁（enable→disable）。
  **已上提：MLF #121 issue → PR #122（OPEN）**，合并后移除容器补丁
