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
>
> 注：ascend CANN 9.0.0 的编译器版本（2026-08-20 实测）——F 列 = flagtree
> 0.6.1+ascend3.5（默认 /opt/flagtree，`import triton` 报模块版本 **3.5.1**）；
> T 列 = vendor triton 3.5.0 + triton_ascend 3.2.1（`compiler triton` →
> /opt/triton，`import triton` 报模块版本 **3.2.0**）。两列均需 **torch-first
> 导入顺序**（`import triton` 先于或独立于 torch 崩：flagtree ascend backend
> discovery 嵌套 import torch → torch_npu autoload 失败，见 training 记录）。

## 矩阵

| 厂商     | 后端          | 训练(T) | 训练(F) | 强化学习(T) | 强化学习(F) | 后训练(T) | 后训练(F) | 推理(T) | 推理(F) |
| -------- | ------------- | ------- | ------- | ----------- | ----------- | --------- | --------- | ------- | ------- |
| 英伟达   | CUDA 12.8     | ✅      | ✅      | ✅          | ✅          | ✅        | ✅        | ✅      | ✅      |
| 英伟达   | CUDA 13.3     | ✅      | ✅      | ✅          | ✅          | ✅        | ✅        | ✅      | ✅      |
| 昇腾     | CANN 8.5.0    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 昇腾     | CANN 9.0.0    | ✅      | ✅      | ⬜          | ⬜          | ✅        | ✅        | ✅      | ✅      |
| 寒武纪   | NEUWARE 4.4.3 | ⬜      | —       | ⬜          | —           | ？        | —         | ⛔      | —       |
| 寒武纪   | NEUWARE 4.7.2 | ⬜      | —       | ⬜          | —           | ？        | —         | ⛔      | —       |
| 燧原     | TOPS 1.9.10   | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 燧原     | TOPS 1.10.6   | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 海光     | DTK 26.04     | ✅      | ✅      | ✅          | ✅          | ✅        | ✅        | ✅      | ✅      |
| 天数智芯 | COREX 4.4.0   | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 昆仑芯   | XRE 5.37.1    | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 沐曦     | MACA 3.7.2.1  | ⬜      | ⬜      | ⬜          | ⬜          | ？        | ？        | ⛔      | ⛔      |
| 沐曦     | MACA 3.8.1.3  | ✅      | ✅      | ✅          | ✅          | ✅        | ✅        | ✅      | ✅      |
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

- **nvidia training（2026-08-19，cuda12.8 双编译器全 ✅）**：h20 runner +
  `megatron-nv128` 容器（flagos-runtime-nvidia-cuda12.8:2.1.2，merged wheel
  `0.17.1+fl.20260818.g48b97a13f1bb` 单步安装）。mock data 5 iter E2E
  **双编译器均 exit 0**——flagtree 3.6.0（默认 /opt/flagtree，iter1 loss
  8.371983E+00）与 vendor triton 3.6.0（`compiler triton` →
  /opt/triton，逐 iter 8.371983/8.363531/8.348538/8.366852/8.357372）；
  **validation loss 两线一致 8.360331E+00**（同 seed 42，mock 数据确定性
  复现）。环境：torch 2.10.0+cu128、flag_gems 5.3.4、numpy 2.3.5。
  **新缺陷：flagtree 线 inductor fork 崩溃**——MLF hyper_connection 硬编码
  `@torch.compile`（9 处）× torch 2.10 inductor 子进程池（默认
  worker_start_method="subprocess"）× flagtree hint_manager 在 fork 出的
  worker 里调 `torch.cuda.current_device()` → "Cannot re-initialize CUDA in
  forked subprocess"（iter 1 backward 崩）。**处置（用法侧规避，不回馈上游）**：
  `TORCHINDUCTOR_COMPILE_THREADS=1` 强制内联编译（submit()/use_process_pool()
  对 compile_threads<=1 短路），无 fork；triton 线该 env 惰性无害。与 hygon
  flagtree 3.6.0 的 cluster_dims 崩溃（§1.4）不同——nvidia 线无 jit 补丁前置，
  `--disable-jit-fuser` 直接够用。启动直跑 pretrain_gpt.py（无 torchrun），
  env:// rendezvous 需显式 MASTER_ADDR/MASTER_PORT/RANK/WORLD_SIZE。
- **nvidia training（2026-08-20，cuda13.3 双编译器全 ✅）**：h20 +
  `megatron-nv133` 容器（flagos-runtime-nvidia-cuda13.3:2.1.2，merged wheel
  `0.17.1+fl.20260818.g48b97a13f1bb` 单步安装）。mock data 5 iter E2E
  **双编译器均 exit 0**——flagtree 3.6.0（默认 /opt/flagtree，iter1 loss
  8.371983E+00）与 vendor triton 3.6.0（`compiler triton` → /opt/triton）；
  **validation loss 两线一致 8.360331E+00**（同 seed 42，与 cuda12.8 完全
  一致——mock 数据确定性复现，跨后端成立）。环境：torch 2.11.0+cu130。
  与 cuda12.8 相同的两个用法侧规避：`TORCHINDUCTOR_COMPILE_THREADS=1`
  （flagtree inductor fork 崩溃，§nvidia training 12.8）+ `--disable-jit-fuser`。
  **新发现的环境缺口：cuda13.3 runtime 缺 psutil**（nv128 有 7.2.2）——
  megatron-core Requires-Dist psutil → 单步 vendor 安装失败
  （"Could not find a version that satisfies the requirement psutil"）；
  处置：aliyun 预装 psutil 后再 vendor 单步安装成功。**应入 nvidia
  deps_app（psutil）**，随 flash-attn wheel 一并落库。
- **nvidia post_training × inference（2026-08-20，cuda13.3 双编译器全 ✅）**：
  两场景均编译器无关路径，同 cuda12.8 配方——post_training = DummyModel +
  `simple_generate`（output shape (1,8)，modelopt 0.45.0 ad-hoc 装入，未入
  镜像，同 hygon §1.3.3 modelopt 决策未决）；inference = legacy
  `StaticInferenceEngine` 3 请求 × 8 tokens（merged wheel 含顶层入口文件
  gpt_builders/model_provider，裸 import 阻塞关闭——cuda13.3 验证同 wheel）。
  F 列 17:31:27 / 17:31:59 UTC exit 0，T 列 17:31:41 / 17:32:17 UTC exit 0。
  环境：torch 2.11.0+cu130。inference 需 `--no-persist-layer-norm`
  （同 cuda12.8 教训：merged wheel 参数默认 persist=True）。
- **nvidia RL（2026-08-19，cuda12.8 双编译器全 ✅）**：h20 + `megatron-nv128`
  容器，merged wheel `0.17.1+fl.20260818.g48b97a13f1bb`，前置 = MLF PR #116
  5 补丁（RL local-impl，容器 site-packages 直打）+ 自建 flash-attn wheel
  `2.8.3.post1+fl.cu128.torch210`（§5.5 动态引擎硬依赖）。同 metax 配方
  （`--transformer-impl local` 无 vendor TE、`--rl-partial-rollouts`、
  `--return-log-probs`、`--skip-train --no-load-optim`、dynamic 批参数、
  `TORCHINDUCTOR_COMPILE_THREADS=1` + `--disable-jit-fuser`）——
  **F 列（flagtree 3.6.0 默认线）17:05:09 → 17:05:40 UTC exit 0，T 列
  （vendor triton 3.6.0，`compiler triton`）17:11:21 → 17:11:52 UTC exit 0**。
  两线均 GRPO 迭代 1/20、rollout 8 组、3 次 rollout collection
  （Iteration 0/8/16），triton 线 elapsed 15551.9 ms + Inference
  Coordinator shut down successfully。**真实障碍链（3 个，全 harness 本地）**：
  dummy_agent `isinstance` 缺类参数、TokenRollout `env_id=None`→`""`、
  eod 重复追加（`Only one eod per trajectory` 断言，条件追加 + 掩码按终长）。
  harness 自研不入固化；**固化配方（PR #116 补丁 + 参数集 + flash-attn
  自建 wheel）已由 metax + nvidia 双实证**。运行事实同 metax：每次 relaunch
  前 kill -9 遗留 pretrain 进程；watcher 只信 log "python exit=" 信号。
  对比 hygon：nvidia 线无 jit 补丁前置，`--disable-jit-fuser` 直接够用。
- **nvidia RL（2026-08-20，cuda13.3 双编译器全 ✅）**：h20 + `megatron-nv133`
  容器，merged wheel `0.17.1+fl.20260818.g48b97a13f1bb` 单步安装 + PR #116
  5 补丁（同 nv128 基线，容器 site-packages 直打）+ 自建 flash-attn wheel
  `2.8.3.post1+fl.cu130.torch211`（torch 2.11.0+cu130 ABI，§5.5 动态引擎
  硬依赖）。同 nv128 配方（`--transformer-impl local` 无 vendor TE、
  `--rl-partial-rollouts`、`--return-log-probs`、dynamic 批参数、
  `TORCHINDUCTOR_COMPILE_THREADS=1` + `--disable-jit-fuser`）——
  **F 列（flagtree 3.6.0 默认线）23:21:41 → 23:22:16 UTC exit 0，T 列
  （vendor triton 3.6.0，`compiler triton`）23:23:00 → 23:23:36 UTC exit 0**，
  两线均 GRPO 迭代 1/20、rollout 8 组、3 次 rollout collection（Iteration
  0/8/16），elapsed 17161.8 / 17033.1 ms。**唯一障碍 = nv133 容器缺 rl-extra
  运行时依赖**（相对 nv128 成功基线）：`has_rl_utils` guard 失败——`megatron.rl.rl_utils`
  import 崩于 rl_utils.py:92 `from wandb import wandb_run`
  （ModuleNotFoundError: wandb）；补装 wandb 后仍缺 fastapi/uvicorn/openai/
  tensorboard/transformers（训练链所需），aliyun 全量补装后
  `RL-UTILS-IMPORT-OK` + 全链 exit 0。**该 6 包缺口属容器装配路径问题**
  （直装 wheel 不带 [rl] extra）；app-image 单步 `megatron-core[rl]==…`
  安装无此问题，不入 deps_app。
- **nvidia megatron-rl app image 构建+验证+push（2026-08-20，双后端全 ✅）**：
  `flagos-app/megatron_rl0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f` 与
  `flagos-app/megatron_rl0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f`
  已构建并推送（app 前缀 flagos-app 自 PR #457 起生效；tag 命名 = 应用版本
  0.17.1 + fork 版本 0.2.1_9.g48b97a13f，见 megatron-app-image.yml 头部注释）。
  单步安装 `megatron-core[rl]==0.17.1`
  （wheel `0.17.1+fl.20260818.g48b97a13f1bb`，[rl] extra 全量公共组随
  wheel 装入——RL cuda13.3 记录中的 6 包 ad-hoc 补装缺口在 app-image
  装配路径下不存在）+ APP_DEPS 自建 flash_attn wheel
  （`2.8.3.post1+fl.cu128.torch210` / `+fl.cu130.torch211`，源码构建配方见
  packaging/flash-attn/）。verify 走 --app-image 模式：BEFORE(runtime)
  vs AFTER(app) 矩阵逐包 unchanged——torch 2.10.0+cu128 / 2.11.0+cu130、
  triton MISSING（side-dir /opt/triton 不在 site-packages，与 BEFORE 一致 =
  #458 修复生效判定点）、flag_gems 5.3.4、numpy 2.3.5；`megatron.core`
  import + helpers_cpp bindings OK。**前置缺陷（已修，PR #458）**：
  APP_DEPS 步（flash_attn 安装）缺 `PYTHONPATH="/opt/triton"` guard，
  pip 解析 torch 的 triton==N Requires-Dist 拉新 triton 3.6.0 进
  site-packages，verify 判矩阵变化 abort；与 #456 的 megatron-core 步同款修复，
  dry-run 实证仅装 einops + flash_attn。
- **nvidia megatron-training app image 构建+push（2026-08-20，双后端 ✅）+ h20 E2E
  双编译器复验（cuda12.8）**：`flagos-app/megatron_training0.17.1-nvidia-cuda12.8:
  2.1.2-0.2.1_9.g48b97a13f` 与 `-cuda13.3` 同款 tag 已构建并推送（tag 命名与 RL
  一致：应用版本 0.17.1 + fork 版本 0.2.1_9.g48b97a13f）。app=megatron-training、
  megatron_version=0.17.1、mlf_version=0.2.1_9.g48b97a13f，workflow 内 verify
  （--app-image 模式：BEFORE(runtime) vs AFTER(app) 矩阵逐包 unchanged +
  megatron.core import）双后端均过。training 无 vendor 条件包（configs.yaml
  deps_app.megatron-training = `[]`，仅 RL 有 flash_attn）——镜像 = runtime +
  wheel `[training]` extra 单步安装。**h20 E2E 复验（cuda12.8，`megatron-train-app`
  容器）**：mock data 5 iter 直跑 pretrain_gpt.py，双编译器全 exit 0——flagtree
  3.6.0 默认线与 vendor triton 3.6.0（`compiler triton`）逐 iter loss 完全一致：
  8.371983/8.363531/8.348538/8.366852/8.357372，validation loss test set 两线均
  8.360331E+00（validation set 8.359479E+00）——与矩阵 nvidia training 基线逐位
  一致，app-image 装配路径相对 runtime+wheel 无行为回归（mock 数据确定性）。
- **nvidia post_training × inference（2026-08-19，cuda12.8 双编译器全 ✅）**：
  两场景均编译器无关路径，同 metax 配方——post_training = DummyModel +
  `simple_generate`（output shape (1,8)，nvidia-modelopt 0.45.0 ad-hoc 装入
  runtime venv，aliyun 带依赖解析 PuLP/antlr4-python3-runtime/nvidia-ml-py/
  omegaconf/scipy，torch 2.10.0+cu128 未动，未入镜像——同 hygon §1.3.3
  modelopt 决策未决）；inference = legacy `StaticInferenceEngine` 3 请求 ×
  8 tokens（merged wheel 含顶层入口文件 gpt_builders/model_provider，
  裸 import 阻塞关闭）。F 列 17:15:20 / 17:16:29 UTC exit 0，T 列 17:15:38 /
  17:16:51 UTC exit 0。**唯一障碍：inference 首跑漏传
  `--no-persist-layer-norm`** → `torch_norm.py:48` 断言（torch LayerNorm 不支持
  persist_layer_norm）——合并 wheel 参数默认 persist=True，训练配方参数集需
  逐参数随行（同 §1.6 merged wheel 参数接口重构的教训）。
- **ascend CANN 9.0.0 training（2026-08-20，双编译器全 ✅）**：hw25（910B4，
  aarch64）+ `megatron-ascend900` 容器（flagos-runtime-ascend-cann9.0.0，merged
  wheel `0.17.1+fl.20260818.g48b97a13f1bb` 单步安装）。mock data 5 iter E2E
  **双编译器均 exit 0**——F 列 flagtree 0.6.1+ascend3.5（默认 /opt/flagtree，
  模块版本 3.5.1）与 T 列 vendor triton 3.5.0 + triton_ascend 3.2.1
  （`compiler triton` → /opt/triton，模块版本 3.2.0）；**逐 iter loss 两线
  完全一致**：1.084308/1.084362/1.084429/1.083861/1.083677，validation
  test set 两线均 1.084173E+01（mock 数据确定性复现，与 hygon/metax 量级
  一致）。环境：python 3.11、torch 2.10.0+cpu + torch-npu 2.10.0、
  ASCEND_VISIBLE_DEVICES=0。**用法侧要求（ascend 特有）**：torch-first
  导入顺序——`import triton` 先于或独立于 torch 崩（flagtree ascend backend
  discovery 嵌套 import torch → torch_npu autoload 失败），driver 统一
  torch-first；docker exec 须经 bash -c 进容器（ASCEND 环境已内置，不加
  source）。无 jit 补丁前置，`--disable-jit-fuser` 直接够用。
- **ascend CANN 9.0.0 post_training × inference（2026-08-20，双编译器全 ✅）**：
  两场景均编译器无关路径，同 nvidia/metax 配方——post_training = DummyModel +
  `simple_generate`（output shape (1,8)，modelopt 0.45.0 ad-hoc 装入，
  aliyun 带依赖解析，含 requests/huggingface_hub 传递依赖链，未入镜像，同
  hygon §1.3.3 modelopt 决策未决）；inference = legacy `StaticInferenceEngine`
  3 请求 × 8 tokens。F/T 双线均 exit 0。**唯一障碍：post_training 首跑漏传
  `--no-persist-layer-norm`** → `torch_norm.py:48` 断言（merged wheel 参数
  默认 persist=True，同 nvidia cuda12.8 inference 教训——训练配方参数集需
  逐参数随行）；补传后 F/T 双线全过。
- **ascend megatron-training app image 构建+验证+push（2026-08-20，✅）**：
  `flagos-app/megatron_training0.17.1-ascend-cann9.0.0:2.1.2-0.2.1_9.g48b97a13f`
  已构建并推送（tag 命名与 nvidia 一致：应用版本 0.17.1 + fork 版本
  0.2.1_9.g48b97a13f）。app=megatron-training、megatron_version=0.17.1、
  mlf_version=0.2.1_9.g48b97a13f，workflow 内 verify（--app-image 模式：
  BEFORE(runtime) vs AFTER(app) 矩阵逐包 unchanged + megatron.core import +
  helpers_cpp bindings OK）通过后 push。training 无 vendor 条件包
  （deps_app.megatron-training = `[]`）——镜像 = runtime + wheel
  `[training]` extra 单步安装（wheel 已上传 flagos-pypi-ascend，
  cp311 aarch64）。
- **ascend RL 路径（2026-08-20，三处代码级障碍实证 + 修复上提；全链 E2E
  暂停）**：在 910B（CANN 9.0.0，torch_npu + TORCH_TRANSFER_TO_NPU）上以
  `--transformer-impl local --attention-backend unfused` 跑通 GRPO 训练链
  （rollout → 参考 logprobs → 训练步，exit 0；unfused 路径绕开 flash_attn
  硬依赖），暴露三处代码级问题，均已修复并上提：
  1. **packed_seq 无条件构造（MLF issue #118 + PR #119，NVIDIA #6708 +
     #6709，均 OPEN）**：`get_logprobs` 与 `train_rl.py` forward_step 在
     sequence_packing=False 时无条件构造单序列 thd packed_seq_params（CUDA
     graph 签名一致性）→ `--transformer-impl local` 非融合
     DotProductAttention 断言（Packed sequence is not supported）。修复 =
     仅 `rl_training_cuda_graphs` 开启时构造（单序列 thd == dense），关闭时
     保持 None 走 unfused 路径。非 TE RL 训练前置，已实证。
  2. **KV-append 内核设备断言（MLF PR #120，NVIDIA #6729 + #6730，均
     OPEN）**：`triton_append_key_value_cache` 输入校验硬断言 CUDA → 黑名单
     `not in ('cpu','meta')`（内核纯 Triton 设备无关；910B NPU Triton
     backend 实跑通过——动态批推理 KV-append 路径前置）。PR #120 主体的
     NPU paged attention 平台化（paged-attention capability hooks + NPU
     dispatch + dist.gather_object 兼容）同属该路径前置。
  3. **flagtree nvidia driver is_active（FlagTree issue #1022 + PR #1023，
     均 OPEN）**：TORCH_TRANSFER_TO_NPU shim 伪造 `torch.cuda.is_available()`
     （不伪造 `torch.version.cuda`）→ nvidia + ascend 双后端 is_active 全
     True → `triton.runtime.driver._create_driver()` 崩。修复 = nvidia
     is_active 增加 `torch.version.cuda is not None`（与上游 triton nvidia
     driver 同款守卫；修复后 amd=False, ascend=True, nvidia=False →
     NPUDriver）。
  **RL 全链 E2E 暂停（矩阵 ⬜）**：默认 fused 路径动态引擎硬依赖 flash_attn
  （attention.py:677）——用户已查证（2026-08-20）：Ascend 950 之前的型号
  （含 910B4 = hw25）不支持 flash_attn，vendor 包路线关闭；候选替代 =
  torch_npu `npu_fusion_attention`（TND varlen）映射
  `flash_decode_and_prefill` 的 prefill 分支（`flash_attn_varlen_func`）
  与 decode 分支（`flash_attn_with_kvcache`），paged kv（block_table）需
  先还原为连续 TND 布局——**方案待用户权衡**。unfused 可跑通但非生产路径。
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
- **metax RL（双编译器全 ✅；实证链终止 2026-08-19）**：F 列 = 默认编译器
  flagtree 线（/flagos env，`triton 3.6.0` 即 flagtree 0.6.1+metax3.6 的模块版本）；
  **T 列 = vendor triton 线（`compiler triton` → `triton 3.6.0`
  /opt/triton/triton/__init__.py），07:10:11 → 07:11:37 UTC exit 0**，同配方全链
  通过（rollout 8 组，GRPO 迭代 1/20，elapsed 30727 ms，0 错误）。真实障碍链
  （17 个，全 E2E 实证）全为本地代码/参数/harness 缺陷——
  NullTokenizer pad/bos/eos 缺口、`--return-log-probs` 未注册、dynamic 批参协调
  （`max_tokens<max_requests` 断言）、`[rl]` extra 运行时依赖缺失
  （pyzmq/msgpack/quart/hypercorn/datasets）、flash_attn 2.6.3 的
  `flash_decode_and_prefill` 仅 fp16/bf16（`--bf16` 规避）、torch inductor
  异步编译 × metax driver `current_device()` fork 崩溃
  （`TORCHINDUCTOR_COMPILE_THREADS=1`）、非 streaming drain 断言
  （`--rl-partial-rollouts`）、harness eod 去重。**两处环境不合规均实证非阻塞**：
  无 vendor TE（`--transformer-impl local` 全程无 TE）+ flash_attn 2.6.3 版本断言
  不达标但功能支持 block_table 路径（断言是版本号检查非功能检查，对 vendor 变体
  不适用）。**固化清单见状态文档 #6（5 补丁 + 4 配方参数）**。运行事实：GPU 0 忙
  → `CUDA_VISIBLE_DEVICES=1`；每次 relaunch 前 kill -9 遗留 pretrain 进程；
  watcher 只信 log "python exit=" 信号 + 25min 停滞双条件。
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
  - **状态**：全范围 wheel 从打包侧关闭阻塞，nvidia cuda12.8（2026-08-19）
    与 metax 已验证 ✅，其余后端推理列仍 ⛔ —— 待按序验证。结构性问题
    （决策4 关联："顶层文件作入口"模式不支持 wheel 包发布）仍然成立，
    但不阻塞交付。
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
