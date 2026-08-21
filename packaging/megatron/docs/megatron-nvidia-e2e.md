# Megatron-LM-FL nvidia E2E 验证记录

**验证环境:** 8× H100，runtime 镜像
`flagos-runtime-nvidia-cuda12.8:2.1.2`（torch 2.10.0+cu128）与
`flagos-runtime-nvidia-cuda13.3:2.1.2`（torch 2.11.0+cu130）。
**安装形态:** merged wheel `0.17.1+fl.20260818.g48b97a13f1bb` 单步安装
（[training]/[rl] extra 随 wheel 装入；该 wheel 来自 MLF 分支
ci/merge-105-106-107-114，先于 PR #114 合并）。
**验证周期:** 2026-08-19 ~ 2026-08-20。

场景组织：每场景 = 双后端 × 双编译器（F 列 flagtree 3.6.0 默认 /opt/flagtree，
T 列 vendor triton 3.6.0 `compiler triton` → /opt/triton）。跨后端通用事实
（merged wheel 参数接口、inference 裸 import、依赖面分析）见
[[megatron-verification-matrix.md]] 事实段；编译链问题见
[[megatron-hygon25-e2e.md]]（§1.4 jit_fuser、§5.5 flash_attn 动态引擎硬依赖）。

## training

### cuda12.8（2026-08-19，双编译器全 ✅）

（flagos-runtime-nvidia-cuda12.8:2.1.2，merged wheel
`0.17.1+fl.20260818.g48b97a13f1bb` 单步安装）。mock data
5 iter E2E **双编译器均 exit 0**——flagtree 3.6.0（默认 /opt/flagtree，
iter1 loss 8.371983E+00）与 vendor triton 3.6.0（`compiler triton` →
/opt/triton，逐 iter 8.371983/8.363531/8.348538/8.366852/8.357372）；
**validation loss 两线一致 8.360331E+00**（同 seed 42，mock 数据确定性复现）。
环境：torch 2.10.0+cu128、flag_gems 5.3.4、numpy 2.3.5。
**新缺陷：flagtree 线 inductor fork 崩溃**——MLF hyper_connection 硬编码
`@torch.compile`（9 处）× torch 2.10 inductor 子进程池（默认
worker_start_method="subprocess"）× flagtree hint_manager 在 fork 出的
worker 里调 `torch.cuda.current_device()` → "Cannot re-initialize CUDA in
forked subprocess"（iter 1 backward 崩）。**处置（用法侧规避，不回馈上游）**：
`TORCHINDUCTOR_COMPILE_THREADS=1` 强制内联编译（submit()/use_process_pool()
对 compile_threads<=1 短路），无 fork；triton 线该 env 惰性无害。与 hygon
flagtree 3.6.0 的 cluster_dims 崩溃（hygon 报告 §1.4）不同——nvidia 线无
jit 补丁前置，`--disable-jit-fuser` 直接够用。启动直跑 pretrain_gpt.py
（无 torchrun），env:// rendezvous 需显式 MASTER_ADDR/MASTER_PORT/RANK/
WORLD_SIZE。

### cuda13.3（2026-08-20，双编译器全 ✅）

（flagos-runtime-nvidia-cuda13.3:2.1.2，merged wheel
`0.17.1+fl.20260818.g48b97a13f1bb` 单步安装）。mock data 5 iter E2E
**双编译器均 exit 0**——flagtree 3.6.0（默认 /opt/flagtree，iter1 loss
8.371983E+00）与 vendor triton 3.6.0（`compiler triton` → /opt/triton）；
**validation loss 两线一致 8.360331E+00**（同 seed 42，与 cuda12.8 完全一致——
mock 数据确定性复现，跨后端成立）。环境：torch 2.11.0+cu130。
与 cuda12.8 相同的两个用法侧规避：`TORCHINDUCTOR_COMPILE_THREADS=1`
（flagtree inductor fork 崩溃，见 cuda12.8 training）+ `--disable-jit-fuser`。
**新发现的环境缺口：cuda13.3 runtime 缺 psutil**（cuda12.8 runtime 有 7.2.2）——
megatron-core Requires-Dist psutil → 单步 vendor 安装失败
（"Could not find a version that satisfies the requirement psutil"）；
处置：aliyun 预装 psutil 后再 vendor 单步安装成功。psutil 是公共
PyPI 包（非 vendor 条件包），归属待定——不入 deps_app，候选 =
cuda13.3 runtime deps 补入或 wheel extra（见矩阵跟踪表 #13）。

## post_training × inference

### cuda12.8（2026-08-19，双编译器全 ✅）

两场景均编译器无关路径，同 metax 配方——post_training = DummyModel +
`simple_generate`（output shape (1,8)，nvidia-modelopt 0.45.0 ad-hoc 装入
runtime venv，aliyun 带依赖解析 PuLP/antlr4-python3-runtime/nvidia-ml-py/
omegaconf/scipy，torch 2.10.0+cu128 未动，未入镜像——同 hygon 报告 §1.3.3
modelopt 决策未决）；inference = legacy `StaticInferenceEngine` 3 请求 ×
8 tokens（merged wheel 含顶层入口文件 gpt_builders/model_provider，
裸 import 阻塞关闭）。F/T 双线均 exit 0。**唯一障碍：inference 首跑漏传
`--no-persist-layer-norm`** → `torch_norm.py:48` 断言（torch LayerNorm 不支持
persist_layer_norm）——合并 wheel 参数默认 persist=True，
训练配方参数集需逐参数随行（同 hygon 报告 §1.6 merged wheel 参数接口重构的教训）。

### cuda13.3（2026-08-20，双编译器全 ✅）

两场景均编译器无关路径，同 cuda12.8 配方——post_training = DummyModel +
`simple_generate`（output shape (1,8)，modelopt 0.45.0 ad-hoc 装入，
未入镜像，同 hygon 报告 §1.3.3 modelopt 决策未决）；inference = legacy
`StaticInferenceEngine` 3 请求 × 8 tokens（merged wheel 含顶层入口文件
gpt_builders/model_provider，裸 import 阻塞关闭——cuda13.3 验证同 wheel）。
F/T 双线均 exit 0。
环境：torch 2.11.0+cu130。inference 需 `--no-persist-layer-norm`
（同 cuda12.8 教训：merged wheel 参数默认 persist=True）。

## RL

### cuda12.8（2026-08-19，双编译器全 ✅）

merged wheel
`0.17.1+fl.20260818.g48b97a13f1bb`，前置 = MLF PR #116 5 补丁（RL
local-impl，容器 site-packages 直打）+ 自建 flash-attn wheel
`2.8.3.post1+fl.cu128.torch210`（hygon 报告 §5.5：flash_attn dynamic
引擎硬依赖 ≥2.7.3）。同 metax 配方（[[megatron-metax-e2e.md]] RL：
`--transformer-impl local` 无 vendor TE、`--rl-partial-rollouts`、
`--return-log-probs`、`--skip-train --no-load-optim`、dynamic 批参数、
`TORCHINDUCTOR_COMPILE_THREADS=1` + `--disable-jit-fuser`）——
**F 列（flagtree 3.6.0 默认线）与 T 列（vendor triton 3.6.0，
`compiler triton`）均 exit 0**。
两线均 GRPO 迭代 1/20、rollout 8 组、3 次 rollout collection
（Iteration 0/8/16），triton 线 elapsed 15551.9 ms + Inference
Coordinator shut down successfully。**真实障碍链（3 个，全 harness 本地）**：
dummy_agent `isinstance` 缺类参数、TokenRollout `env_id=None`→`""`、
eod 重复追加（`Only one eod per trajectory` 断言，条件追加 + 掩码按终长）。
harness 自研不入固化；**固化配方（PR #116 补丁 + 参数集 + flash-attn
自建 wheel）已由 metax + nvidia 双实证**。运行事实同 metax：每次 relaunch
前 kill -9 遗留 pretrain 进程；watcher 只信 log "python exit=" 信号。
对比 hygon：nvidia 线无 jit 补丁前置，`--disable-jit-fuser` 直接够用。

### cuda13.3（2026-08-20，双编译器全 ✅）

merged wheel
`0.17.1+fl.20260818.g48b97a13f1bb` 单步安装 + PR #116 5 补丁（同 cuda12.8
基线，容器 site-packages 直打）+ 自建 flash-attn wheel
`2.8.3.post1+fl.cu130.torch211`（torch 2.11.0+cu130 ABI，hygon 报告 §5.5：
flash_attn dynamic 引擎硬依赖）。同 cuda12.8 配方（`--transformer-impl local`
无 vendor TE、`--rl-partial-rollouts`、`--return-log-probs`、dynamic 批参数、
`TORCHINDUCTOR_COMPILE_THREADS=1` + `--disable-jit-fuser`）——
**F 列（flagtree 3.6.0 默认线）与 T 列（vendor triton 3.6.0，
`compiler triton`）均 exit 0**，
两线均 GRPO 迭代 1/20、rollout 8 组、3 次 rollout collection（Iteration
0/8/16），elapsed 17161.8 / 17033.1 ms。**唯一障碍 = cuda13.3 容器缺 rl-extra
运行时依赖**（相对 cuda12.8 成功基线）：`has_rl_utils` guard 失败——
`megatron.rl.rl_utils` import 崩于 rl_utils.py:92 `from wandb import
wandb_run`（ModuleNotFoundError: wandb）；补装 wandb 后仍缺
fastapi/uvicorn/openai/tensorboard/transformers（训练链所需），aliyun
全量补装后 `RL-UTILS-IMPORT-OK` + 全链 exit 0。
**该 6 包缺口属容器装配路径问题**（直装 wheel 不带 [rl] extra）；app-image 单步
`megatron-core[rl]==…` 安装无此问题，不入 deps_app。

## app image（2026-08-20，双后端全 ✅）

### megatron-rl

`flagos-app/megatron_rl0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f`
与 `flagos-app/megatron_rl0.17.1-nvidia-cuda13.3:2.1.2-0.2.1_9.g48b97a13f`
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
PR #458 修复生效判定点）、flag_gems 5.3.4、numpy 2.3.5；`megatron.core`
import + helpers_cpp bindings OK。**前置缺陷（已修，PR #458）**：
APP_DEPS 步（flash_attn 安装）缺 `PYTHONPATH="/opt/triton"` guard，
pip 解析 torch 的 triton==N Requires-Dist 拉新 triton 3.6.0 进
site-packages，verify 判矩阵变化 abort；与 PR #456 的 megatron-core 步同款修复，
dry-run 实证仅装 einops + flash_attn。

### megatron-training（构建+push）+ E2E 双编译器复验（cuda12.8）

`flagos-app/megatron_training0.17.1-nvidia-cuda12.8:2.1.2-0.2.1_9.g48b97a13f`
与 `-cuda13.3` 同款 tag 已构建并推送（tag 命名与 RL
一致：应用版本 0.17.1 + fork 版本 0.2.1_9.g48b97a13f）。app=megatron-training、
megatron_version=0.17.1、mlf_version=0.2.1_9.g48b97a13f，workflow 内 verify
（--app-image 模式：BEFORE(runtime) vs AFTER(app) 矩阵逐包 unchanged +
megatron.core import）双后端均过。training 无 vendor 条件包（configs.yaml
deps_app.megatron-training = `[]`，仅 RL 有 flash_attn）——镜像 = runtime +
wheel `[training]` extra 单步安装。**E2E 复验（cuda12.8）**：mock data
5 iter 直跑 pretrain_gpt.py，
双编译器全 exit 0——flagtree 3.6.0 默认线与 vendor triton 3.6.0
（`compiler triton`）逐 iter loss 完全一致：8.371983/8.363531/8.348538/
8.366852/8.357372，validation loss test set 两线均 8.360331E+00
（validation set 8.359479E+00）——与矩阵 nvidia training 基线逐位一致，
app-image 装配路径相对 runtime+wheel 无行为回归（mock 数据确定性）。
