# 燧原 GCU — torch-gcu `all_gather_object` sizes 回传垃圾值 / ECCL 拒绝 fp64 all_reduce（缺陷报告）

**日期：** 2026-08-31　**报告人：** FlagOS 集成验证

**硬件：** ENFLAME GCU 48G（vm-dhrj-gd-zone7-d-s60-48g-1-48）　**宿主驱动：** 1.10.6

**场景：** megatron-core 0.17.1 training（单卡，`pretrain_gpt.py` mock-data E2E）在两个 runtime 上分别验证：
TOPS 1.9.10 与 TOPS 1.10.6。共命中两个 vendor 侧集合通信缺陷，均已用 MLF 侧 workaround 绕过（见文末）。

---

## 缺陷 1：`torch.distributed.all_gather_object` sizes 回传垃圾值

**涉及组件：** torch-gcu　**复现版本：** TOPS 1.9.10（torch-gcu 2.10.0+3.7.20260408）

**触发点：** `megatron/core/optimizer/__init__.py` 参数组对齐：

```python
gathered_params_key = [None for _ in range(torch.distributed.get_world_size())]
torch.distributed.all_gather_object(gathered_params_key, params_key)
```

**现象：** 单卡（WORLD_SIZE==1）运行时，`all_gather_object` 内部对对象 **sizes** 的 all_gather 回传垃圾值——本地 rank 收到的 max object size 为 `-4888733163028742123`，随后 `input_tensor.resize_(max_object_size)` 按 ~1 EB 申请内存直接 OOM。`torch.gcu.synchronize()` 无效；普通 `all_gather`（各 dtype）均正常。

**期望：** WORLD_SIZE==1 时 sizes 交换应返回真实值（即 gather 语义本身为 no-op）。

**影响：** 单卡训练在启动期即崩溃，无法绕过（应用层唯一缓解 = 跳过该集合通信）。

---

## 缺陷 2：ECCL 拒绝 fp64 `all_reduce`（`ecclInvalidArgument`）

**涉及组件：** ECCL（v3.6.3.11）　**复现版本：** TOPS 1.10.6（torch-gcu 2.11.0+3.8.20260713）

**触发点：** `megatron/training/training.py` 启动 timestamp 全局最小化同步（两处）：

```python
program_start_global = torch.tensor([_STARTUP_TIMESTAMPS['program_start']], dtype=torch.double, device='cuda')
torch.distributed.all_reduce(program_start_global, op=torch.distributed.ReduceOp.MIN)
```

**现象：** `dtype=torch.double` 的 `all_reduce` 直接抛 `DistBackendError: ECCL error … ecclInvalidArgument`，训练在首步前中止。改用 `torch.float32` 后两处均正常通过。

**版本差异：** 同一份代码在 TOPS 1.9.10（ECCL 3.6.3.11）上**未触发**，仅 1.10.6 需要 workaround——疑与 ECCL 版本或 torch-gcu 版本相关，请厂商确认 fp64 支持边界。

**影响：** 双编译器（flagtree / triton）路径均受影响；fp32 为唯一已实证可用的替代 dtype。

---

## 现状

- FlagOS 已在 Megatron-LM-FL 提交 workaround（已开源，供复现参考）：
  - MLF PR [#130](https://github.com/flagos-ai/Megatron-LM-FL/pull/130)：WORLD_SIZE==1 短路 `all_gather_object`（缺陷 1）。
  - MLF PR [#131](https://github.com/flagos-ai/Megatron-LM-FL/pull/131)：timestamp 同步改 fp32（缺陷 2）。
- 缺陷 1 与缺陷 2 均为 **vendor 侧集合通信库**行为，workaround 仅覆盖单卡场景；多卡 + 对象 gather / fp64 同步在修复前仍有风险。
