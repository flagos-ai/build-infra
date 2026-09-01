# Megatron-LM-FL enflame E2E 验证记录

## enflame-tops1.9.10（2026-08-31）

验证在 vm-dhrj-gd-zone7-d-s60-48g-1-48（ENFLAME GCU 48G 节点，`ssh enflame`，
user `secure`）上进行，**GCU 1**（`ENFLAME_VISIBLE_DEVICES=1`，避开 0 号与镜像
制作冲突）。runtime 镜像 `flagos-runtime-enflame-tops1.9.10:2.1.2`，Python
3.12。宿主驱动 1.10.6；TOPS Runtime 1.9.10（topsruntime/topscc/topspti/topstx
均 1.9.10，topsaten 3.7.20260514，ECCL 3.6.3.11）。torch 2.10.0+cpu +
torch-gcu 2.10.0+3.7.20260408，flagtree 0.6.0+enflame3.6（默认 /flagos），
triton 3.6.0 + triton_gcu 3.6.0+1.0.20260521.cc.1.9.10（/opt/triton），
flag_gems 5.3.5。megatron-core 安装形态为 MLF 集成分支 `ci/enflame` 重建的
wheel `0.17.1+fl.20260831.gc32a6e40e45d`（cherry-pick
[MLF #105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105) /
[MLF #106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106) /
[MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) /
[MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114) /
[MLF #122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122) /
[MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125) /
[MLF #130](https://github.com/flagos-ai/Megatron-LM-FL/pull/130) /
[MLF #131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)），`pip install`
单步安装（无 `--no-deps`）。

**结论：** training 场景双编译器（flagtree / triton）全部打通，mock-data
`pretrain_gpt.py` 5 iters 均 exit 0（RC 显式捕获于容器 /tmp/*_rerun_rc.txt）。
F/T 两路径 loss 完全一致，且与 1.10.6 已记录值逐位一致（iter1 1.090257E+01、
val 1.088866E+01、test 1.088891E+01）。**新 wheel 无需任何容器侧补丁**——旧
wheel（`0.17.1+fl.20260822.g56acf36bacd1`）需要的两个 sed 补丁已被上游修复
取代：

1. **flagtree 线 jit_fuser 陷阱（同 hygon §1.4 / 1.10.6 记录）**：
   `megatron/core/jit.py:21` import 期即绑定 `jit_fuser = torch.compile`，
   flagtree 编译器路径下 inductor warmup 触发
   `InductorError: No module named 'triton_gcu'`。上游改为惰性装饰器
   （[MLF #122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122)），双路径
   均不再需要 sed。
2. **ECCL all_gather_object sizes 回传垃圾值**（vendor 缺陷，缺陷报告见
   [../handoffs/enflame-torch-gcu-all-gather-object-garbage.md](../handoffs/enflame-torch-gcu-all-gather-object-garbage.md)）：
   `megatron/core/optimizer/__init__.py:369` —— ECCL/torch-gcu
   2.10.0+3.7.20260408 上 `all_gather_object` 的 sizes all_gather 回传垃圾值
   （repro：本地 rank 收回来 -4888733163028742123 →
   `input_tensor.resize_(max_object_size)` 1EB OOM）；`torch.gcu.synchronize()`
   无效；普通 all_gather 各 dtype 全对。上游以 world_size==1 短路取代调用
   （[MLF #130](https://github.com/flagos-ai/Megatron-LM-FL/pull/130)，
   WORLD_SIZE==1 语义安全），wheel 内已生效。

**与 1.10.6 的差异：** 旧 wheel 上 1.9.10 无需 fp64 all_reduce 补丁（1.10.6
需要打）；新 wheel 已含上游 [MLF #131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)
（fp64 → float32）修复后，两后端均无补丁直跑。

---

## enflame-tops1.10.6（2026-08-31）

验证在 vm-dhrj-gd-zone7-d-s60-48g-1-48（ENFLAME GCU 48G 节点，`ssh enflame`，
user `secure`）上进行，runtime 镜像 `flagos-runtime-enflame-tops1.10.6:2.1.2`，
Python 3.12，torch 2.11.0+cpu + torch-gcu 2.11.0+3.8.20260713，flagtree
0.6.1+enflame3.6，triton 3.6.0（+ triton-gcu post-install）。megatron-core
安装形态为 MLF 集成分支 `ci/enflame` 重建的 wheel
`0.17.1+fl.20260831.gc32a6e40e45d`（cherry-pick
[MLF #105](https://github.com/flagos-ai/Megatron-LM-FL/pull/105) /
[MLF #106](https://github.com/flagos-ai/Megatron-LM-FL/pull/106) /
[MLF #107](https://github.com/flagos-ai/Megatron-LM-FL/pull/107) /
[MLF #114](https://github.com/flagos-ai/Megatron-LM-FL/pull/114) /
[MLF #122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122) /
[MLF #125](https://github.com/flagos-ai/Megatron-LM-FL/pull/125) /
[MLF #130](https://github.com/flagos-ai/Megatron-LM-FL/pull/130) /
[MLF #131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)），`pip install`
单步安装（无 `--no-deps`）。验证周期 2026-08-31。

本报告只记录**可复现的技术发现与缺口**，不含瞬时错误与一次性环境故障。

## 0. Summary

**结论：** training 场景双编译器（flagtree / triton）全部打通，mock-data
`pretrain_gpt.py` 5 iters 均 exit 0，**无任何容器侧补丁**——旧 wheel 需要的
sed 补丁已被 wheel 内上游修复取代：

1. **flagtree 线 jit_fuser 陷阱（同 hygon §1.4）**：`megatron/core/jit.py`
   import 期即绑定 `jit_fuser = torch.compile`，flagtree 编译器路径下
   inductor warmup 触发 `InductorError: No module named 'triton_gcu'`
   （flagtree PYTHONPATH 上无 triton_gcu）。`--disable-jit-fuser` 太晚。
   上游改为惰性装饰器（[MLF #122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122)），
   wheel 内生效。
2. **双路径 ECCL fp64 all_reduce 限制**（vendor 缺陷，上游修复已提
   [MLF #131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)）：
   ECCL（enflame 的 NCCL 模拟，v3.6.3.11）拒绝 fp64 all_reduce——启动
   timestamp 同步处 `torch.distributed.all_reduce(..., dtype=torch.double)`
   直接抛 `DistBackendError: ECCL error … ecclInvalidArgument`。
   [MLF #131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)
   改为 float32 后 wheel 内生效。

| 场景 | 状态 | 一句话事实 |
|---|---|---|
| training | ✅ 通过 | 双编译器直跑 `pretrain_gpt.py` exit 0；F/T loss 完全一致 |
| post_training | ? 未验证 | — |
| inference | ⛔ 挂起 | 同矩阵其余未验后端（上游阻塞） |
| rl | ⛔ 挂起 | 上游阻塞（[MLF #116](https://github.com/flagos-ai/Megatron-LM-FL/pull/116)） |

**loss 一致性：** iteration 1/5 loss 1.090257E+01（F=T 相同），test-set
validation loss 1.088891E+01（F=T 完全一致）。前后 snapshot 矩阵
（torch / triton / flag_gems / numpy）逐项相等；`helpers_cpp` 绑定 OK。

**教训清单：**

1. **jit_fuser import 期绑定是 flagtree 线通用陷阱**——与 hygon 同根
   （flagtree 编译器路径缺 triton_gcu），非 enflame 特有；上游已修复
   （[MLF #121](https://github.com/flagos-ai/Megatron-LM-FL/issues/121) →
   [MLF #122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122)），已并入
   集成分支 wheel。
2. **ECCL 的 fp64/int64 all_reduce 不支持**是 enflame 特有（其他厂商
   collectives 接受 double）——megatron training 启动路径显式用
   `dtype=torch.double` 同步 timestamp，非 CUDA 平台移植时需注意；上游
   [MLF #131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)
   已以 fp32 规避。
3. 无需 torch-first import order（与 ascend 不同）；无需额外包。

## 1. 补丁明细

新 wheel（`0.17.1+fl.20260831.gc32a6e40e45d`，MLF 集成分支 `ci/enflame`）
已含上游修复 [MLF #122](https://github.com/flagos-ai/Megatron-LM-FL/pull/122) /
[MLF #130](https://github.com/flagos-ai/Megatron-LM-FL/pull/130) /
[MLF #131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)，无容器侧补丁；
复验时以 `verify-megatron-backend.sh --compiler flagtree|triton` 在 fresh
runtime 容器内先跑 snapshot 矩阵、再跑 import check + mock-data E2E。
