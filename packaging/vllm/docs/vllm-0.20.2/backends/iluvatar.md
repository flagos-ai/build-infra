# vllm 0.20.2 — iluvatar corex4.4.0

> 本文对应原报告第 2 部分 §2.5。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.5 iluvatar-corex4.4.0（负结果：厂商工具链版本过旧）

**日期:** 2026-08-02　**平台:** Iluvatar CoreX (BI 系列)
**节点:** `ix15`（JumpServer 别名，hostname n15）　**CoreX:** 4.4.0
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-iluvatar-corex4.4.0:2.1.1`

**这是首个跑不通推理的后端**，但结论明确、可操作。与 [§2.4](hygon.md) hygon
一样直接复用 mthreads 的 `+flagos` wheel，验证三件事：(1) wheel 跨后端通用；
(2) numpy 版本正确；(3) vllm 推理可跑。前两点通过，第三点**失败**——根因是
iluvatar 的 **corex Triton fork 前端 + torch 2.7.1 相对 vllm 0.20.2 的原生
kernel 过旧**。

### Repack —— 无（复用 mthreads 产物）

同 [§2.4](hygon.md)，不在 iluvatar 上重新 build。直接从 `flagos-pypi-mthreads`
装 [§2.3](mthreads.md) 的三个 `+flagos` wheel（vllm 0.20.2 / xgrammar 0.2.5 /
compressed-tensors 0.15.0.1）。

### 安装 —— ✅ wheel 通用；曾踩到 numpy 单步安装坑（现已修复）

**GOAL 1（wheel 通用性）✅：** 三个 mthreads `+flagos` wheel 在 iluvatar 上
正常安装，torch `2.7.1+corex.4.4.0`、flag_gems、flagtree 全部保留，零泄漏。
**这是 [§5.2](../decisions.md) 通用性的第二个跨后端实证**（继 hygon 之后）。

**GOAL 2（numpy 版本）✅：** iluvatar torch 2.7.1 同样编于 numpy 1.x ABI，
`configs.yaml` 已 pin `numpy==1.26.4`（正确，`tensor.numpy()` 可跑）。

> **当时的坑（现已修复）：** 单步 `pip install vllm==0.20.2+flagos
> numpy==1.26.4` 曾报 `ResolutionImpossible`——`opencv-python-headless` 强声明
> `numpy>=2`（[§1.7](../playbook.md) 的 faked 下限），pip 解析期不认"运行时
> 兼容"，当时只能两步安装（先装 vllm 让 numpy 浮到 2.2.6，再
> `pip install numpy==1.26.4` 降级）。
> **修复：** repack 现在把 opencv 的 `numpy` 声明一并剥掉（`config.yaml` 的
> `strip_extra_from_indirect: {opencv-python-headless: [numpy]}`，
> [§1.3](../playbook.md)），repacked `opencv-python-headless==5.0.0.93+flagos`
> 不再声明 numpy 下限，`numpy==1.26.4` 可直接写进第 1 步——所有
> numpy-1.x-ABI 后端（iluvatar、hygon）单步安装即可，两步绕过成为历史
> （[§1.4](../playbook.md)）。

### 阻塞点：corex Triton fork + torch 2.7.1 对 vllm 0.20.2 原生 kernel 过旧

**GOAL 3（推理）❌**。四个阻塞点，同一根因。iluvatar 的 torch 2.7.1 是四个
后端里最旧的（hygon 2.9.0、mthreads 2.9.1、metax 2.8.0、nvidia 2.10.0），
corex Triton fork 前端也比 vllm 0.20.2 的原生 kernel 所需的更旧、更严格：

| # | 现象 | 性质 | 绕过手段 |
|---|------|------|----------|
| A | `import vllm` 崩：`ImportError: cannot import name '_SymmetricMemory' from 'torch._C._distributed_c10d'` | torch 2.7.1 < 2.8（`_SymmetricMemory` 约 torch 2.8 引入） | vllm `parallel_state.py:42` 的 `import torch.distributed._symmetric_memory` 是**无守卫**的顶层导入；而 vllm 自己在**同类文件** `symm_mem.py:16` 已用 `try/except ImportError` 守卫。给 line 42 补同样的守卫即可 import——TP=1 下 symm_mem 路径根本不走（实际算子在 `parallel_state.py:245` 的 `torch.ops.symm_mem.*`，是 TP>1 collective） |
| B | 采样阶段 Triton 编译崩：`TypeError: Cannot use /, #, or % with triton.language.uint32 and triton.language.int32 ... different signedness` | corex Triton fork 拒绝混合符号运算 | vllm 原生采样 kernel `topk_topp_triton.py` 的 `uint32 // int32`。在 `topk_topp_sampler.py` 强制 `HAS_TRITON=False`，回退到纯 pytorch 采样路径 |
| C | 推理阶段 Triton 编译崩：`AttributeError("'AnnAssign' object has no attribute 'targets'")`，出错行 `left: tl.int32 = 0` | corex Triton 前端解析不了 PEP 526 注解赋值 | vllm 原生 attention kernel `triton_unified_attention.py`。用 plugin 自带 flag `VLLM_FL_USE_FLAGGEMS_ATTN=1` 把 attention 路由到 plugin 的 `AttentionFLBackend`（flag_gems attn，能在 corex 上编译），替代 vllm 原生 `TRITON_ATTN`（默认值，崩）——**这是 plugin 提供的正规开关，非源码 hack** |
| D | 绕过 A–C 后 serve 启动成功（health 200、模型可列），但推理输出**乱码** | 前向数值正确性 | 未找到 |

**关键区分：flag_gems 自带的 Triton kernel（rms_norm、rotary_embedding、
silu_and_mul）在 corex 上编译运行都正常**——它们是针对 corex fork 写的；崩的
全是 **vllm 上游自带的原生 Triton kernel**（B 的采样、C 的 attention），用了
corex 前端不支持的语言特性。

**D 是决定性的坏消息：** 绕过 A–C 后，serve 完整启动、接受请求、返回 24
tokens、HTTP 200，但输出是乱码：`"eld \$不断 the movie...髹 Next..."`。在
**temp=0（确定性 argmax，无采样随机性）** 下**仍是乱码**（`"eld \`vette记者在
ApplicationController\n\n..."`，chat 全是换行）——排除采样，故障锁定在
**前向数值路径**：模型跑完并返回，但 logits 数值是错的。日志里
`rms_norm=['native']`（部分算子回退 torch-native）可能也参与了失配。

> **对照 hygon/mthreads：** 那两个后端 torch ≥2.8、厂商 Triton fork 能吞下
> vllm 原生 kernel，所以只碰到单点的 mul 门控 bug（可修）。iluvatar 不是一个
> bug，是**工具链代差**——corex Triton 前端与 torch 2.7.1 双双落后于 vllm
> 0.20.2 的要求。A、B 施加的都是**诊断补丁**（非生产修复），到 D 停手未再
> 深挖数值 bug。
>
> **注意（诊断组合的局限）：** 强制 flag_gems attention（C）+ 关闭原生采样
> Triton（B）是一个**未经测试的算子组合**，尚不能完全排除它本身就是 D 乱码
> 的成因之一。要定论需在一个 Triton 无障碍的后端上复现同样的
> `VLLM_FL_USE_FLAGGEMS_ATTN=1` + `HAS_TRITON=False` 组合做对照。

### serve + 推理 —— ❌ 乱码（前向数值错误）

```bash
VLLM_FL_USE_FLAGGEMS_ATTN=1 vllm serve /data/Qwen3-4B-Instruct-2507-FlagOS \
  --port 8035 --trust-remote-code --max-model-len 4096 --enforce-eager \
  --gpu-memory-utilization 0.85 --tensor-parallel-size 1
# 另需 A/B 两处诊断补丁：parallel_state.py:42 加守卫、topk_topp_sampler.py HAS_TRITON=False
```

serve 到达 `Application startup complete`，`Using FlagGems attention backend.`，
KV cache 127,024 tokens。但推理（含 temp=0）输出乱码：

```json
{"choices":[{"text":"eld \\`vette记者在 ApplicationController\n\n\n...","finish_reason":"length"}]}
```

### Stack 验证

```
torch:        2.7.1+corex.4.4.0    ✅  from 镜像（未降级，四后端中最旧）
triton:       corex fork           ⚠️  flag_gems 自带 kernel 可编译；vllm 原生 kernel 不可
flagtree:     (镜像自带)            ✅
flag_gems:    5.3.2                 ✅  自带算子编译运行正常（mul 门控 #5130 不影响，device=cuda）
numpy:        1.26.4               ✅  configs.yaml 已 pin（torch 编于 numpy 1.x ABI）
vllm:         0.20.2+flagos        ✅  empty, 复用 mthreads PyPI 产物
vllm_fl:      0.0.0+gd1327ae0a     ✅  纯 Python（无 VLLM_VENDOR）
CoreX device: ✅ 可见               (Iluvatar BI)
vllm import:  ⚠️  需补 symm_mem 守卫（trap A）
vllm serve:   ⚠️  需 B+C 绕过才能启动
Inference:    ❌  乱码（temp=0 仍乱）——前向数值错误（trap D）
```

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| 反馈厂商：corex Triton fork 支持 vllm 原生 kernel | ⬜ 阻塞 | 需支持混合符号运算（B）与 PEP 526 注解赋值（C）；或 FlagGems 提供覆盖全部 vllm 原生 Triton 算子的替代 |
| 反馈厂商：torch 升级到 ≥2.8 | ⬜ 阻塞 | vllm 0.20.2 需要 `_SymmetricMemory`（trap A），corex torch 2.7.1 缺 |
| 前向数值正确性（trap D）| ⬜ 阻塞 | flag_gems 在 corex 上逐算子对数值；先在无 Triton 障碍的后端复现 B+C 组合做对照，排除诊断组合本身 |
| vllm `parallel_state.py:42` 无守卫导入 | ⬜ 可提 upstream/plugin | vllm 自己在 `symm_mem.py:16` 已守卫同一导入；给 line 42 补 `try/except` 对所有 torch<2.8 后端都受益 |
| numpy-1.x 后端单步安装 ResolutionImpossible | ✅ 已修复 | repack 剥掉 opencv 的 faked `numpy>=2`（`strip_extra_from_indirect`，[§1.3](../playbook.md)）；单步安装恢复，[§1.4](../playbook.md) 已更新 |

**相关提交：** 无；复用 [§2.3](mthreads.md) mthreads 的 repack 产物（PR
#280）。诊断补丁（trap A/B）为一次性验证手段，未落库。
