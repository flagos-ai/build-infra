# vllm 0.20.2 — hygon dtk26.04

> 本文对应原报告第 2 部分 §2.4。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.4 hygon-dtk26.04（跨后端通用性验证）

**日期:** 2026-08-02　**平台:** Hygon BW1000 (8× HCU)
**DTK:** 26.04
**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-hygon-dtk26.04:2.1.1`

**这是首个不做本地 repack、直接复用他机 wheel 的后端**——用的正是 [§2.3](mthreads.md)
在 mthreads 上打包上传到 `flagos-pypi-mthreads` 的三个 `+flagos` wheel。目的有
二：(1) 实证 [§5.2](../decisions.md) 的"empty wheel 跨后端通用"；(2) 摸清 Hygon
上 vllm 推理的坑。结论：**通用性成立**，唯一真阻塞是镜像侧的 torch↔numpy ABI
不匹配。

> **容器启动（DCU 直通）：** docker 默认 runtime 已是 `dcu`；仍显式带上设备
> 与 HAL 挂载：
> ```bash
> docker run -d --network host --runtime dcu \
>   --device /dev/kfd --device /dev/mkfd --device /dev/dri --group-add video \
>   -v /opt/hyhal:/opt/hyhal -v /data:/data \
>   harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.1.1 sleep infinity
> ```
> `hy-smi` 在容器内可见 8× HCU（宿主机无此命令）。

### Repack —— 无（复用 mthreads 产物）

不在 Hygon 上重新 build/repack。empty vllm 是纯 Python `py3-none-any`，repack
只清理 METADATA 依赖声明、不含硬件代码，因此**一份 wheel 通用于所有 empty
后端**（[§5.2](../decisions.md)）。直接从 `flagos-pypi-mthreads` 装
[§2.3](mthreads.md) 的三个包：

| 包 | 版本 | 来源 |
|------|------|------|
| vllm | 0.20.2+flagos | `flagos-pypi-mthreads`（[§2.3](mthreads.md) 打包） |
| xgrammar | 0.2.5+flagos | 同上 |
| compressed-tensors | 0.15.0.1+flagos | 同上 |

### 安装 —— ✅ 单步，零泄漏（跨后端通用性实证）

按 [§1.4](../playbook.md) 单步安装，但**主索引指向 mthreads 的 PyPI**（而非
hygon 自己的）：

```bash
VENDOR=https://resource.flagos.net/repository/flagos-pypi-mthreads/simple
ALIYUN=https://mirrors.aliyun.com/pypi/simple
pip install --index-url "$VENDOR" --extra-index-url "$ALIYUN" vllm==0.20.2+flagos
```

`pip install --dry-run` 的 "Would install" 集合中**零** torch / triton /
numpy / nvidia-* / flag_gems——Hygon 镜像烘焙的版本全部保留：

- `torch` 保持 `2.9.0+das.opt1.dtk2604`（未降级），`triton` 不存在（由
  flagtree 提供，与 mthreads 同）
- `flag_gems` 5.3.2 / `flagtree` 0.5.1+hcu3.1 / `numpy` 2.2.6 全部完好
- 三个 `+flagos` wheel 正确解析
- `vllm-plugin-FL` 纯 Python 安装（`0.0.0+gd1327ae0a`，不设 `VLLM_VENDOR`），
  `fl` 插件正常激活

**这实证了 [§5.2](../decisions.md)：mthreads 上打的 empty wheel 在 Hygon 上
原样可用，vendor PyPI 无须为这些纯 Python 包做 per-vendor repack。**

### 阻塞点：torch↔numpy ABI 不匹配（镜像侧问题，非 vllm 引入）

装完后 `import torch` 警告 `Failed to initialize NumPy: _ARRAY_API not
found`，`tensor.numpy()` 抛 `RuntimeError: Numpy is not available`。

**根因：** 厂商 torch `2.9.0+das.opt1.dtk2604` 编译时链接的是 **numpy 1.x C
ABI**，而镜像烘焙的是 **numpy 2.2.6**（configs.yaml 的 hygon pin）。二分验证：
numpy 1.26.4 → `TORCH_NUMPY_OK`；numpy 2.2.6 → `Numpy is not available`。
**并非 vllm 引入**——numpy 全程保持 2.2.6（安装未改动它），torch 在 baseline
就已经用不了 numpy。与 iluvatar 同类（其 torch 亦编译于 numpy 1.x）。

**挤压效应（伪冲突）：** vllm 依赖 `opencv-python-headless 5.0.0.93` 声明
`numpy>=2; python_version >= "3.9"`，看似与 Hygon torch 的 `numpy<2` 冲突。
**但这个 `>=2` 是 faked（打包策略声明，非运行时 ABI 下限）。** 实测：numpy
1.26.4 下 cv2 5.0.0 的 C-API 往返全部正常——`cvtColor`、`imencode`/`imdecode`
（PNG 无损，`max_err=0`）、`resize`(float64) 均通过。技术原因：numpy 2.0
起，**针对 numpy 2.x 编译的 C 扩展在运行时向后兼容 numpy ≥1.19**，所以
opencv wheel 在 1.26.4 上照跑，只是元数据声明了 `>=2`。因此 opencv **不构成**
numpy 版本的真实约束（这也纠正了历史 numpy saga 的一个前提，见
[§1.7](../playbook.md)、[§6](../playbook.md)）。

**真正的 numpy 下限是厂商 torch 的 ABI，且是非对称的：**
- 针对 numpy **1.x** 编译的 torch（hygon）→ 运行在 numpy 2.x 上**前向不兼容**
  → 硬性要求 `<2`，不可 fake。
- 针对 numpy **2.x** 编译的扩展（opencv、多数后端 torch）→ 向后兼容 1.x。

**修复属镜像侧，两个方向：**
- **(b) configs.yaml 给 hygon pin `numpy==1.26.4`**（即时、在我方掌控内；
  opencv 既是 faked，此路无副作用）——**推荐的即时修复**。
- **(a) 厂商用 numpy 2.x 重编 torch**（与其余后端一致，但需厂商行动、周期长）。

当前 `configs.yaml` 的 `hygon: numpy==2.2.6` 与所发 torch wheel 不兼容——短期
按 (b) 改 1.26.4，同时把 (a) 反馈给构建 DTK26.04 torch wheel 的一方。

> **flag_gems mul 门控 #5130 不影响 Hygon：** Hygon 报
> `device.type=='cuda'`、`torch.cuda.device_count()==8`、flag_gems
> `runtime.device.name=='cuda'`——与 MetaX 同，非 mthreads 的 `"musa"`。故
> [§2.3](mthreads.md) 的 mul 门控回归在此为 no-op。

### serve + 推理 —— ✅ 成功（以 numpy 1.26.4 绕过上述 ABI 阻塞）

选 **Ministral-8B-Instruct-2410-FlagOS**（简单 rope，变量最少）：

```bash
vllm serve /data/Ministral-8B-Instruct-2410-FlagOS --port 8033 \
  --trust-remote-code --max-model-len 4096 --enforce-eager \
  --gpu-memory-utilization 0.85 --tensor-parallel-size 1
```

serve 到达 `Application startup complete`，flag_gems 算子经插件正确分发：

```
Op 'rms_norm' using 'default.flagos' (kind=flagos, vendor=None)
Op 'rotary_embedding' using 'default.flagos' (kind=flagos, vendor=None)
Op 'silu_and_mul' using 'default.flagos' (kind=flagos, vendor=None)
```

```json
{"choices":[{"text":" Paris. It is the most populous city in France and the country's center of politics, culture, fashion, food, and art. Paris is known for",
  "finish_reason":"length"}]}
```

✅ 除 numpy 绕过外，本模型无需任何 Hygon 专属 plugin / flag_gems 改动。

### Stack 验证

```
torch:        2.9.0+das.opt1.dtk2604  ✅  from 镜像（未降级）
triton:       (absent)                ✅  DTK 无 triton，由 flagtree 提供
flagtree:     0.5.1+hcu3.1            ✅
flag_gems:    5.3.2                   ✅  mul 门控 #5130 不影响（device=cuda）
numpy:        1.26.4 (绕过)           ⚠️  镜像默认 2.2.6 与 torch ABI 不匹配
vllm:         0.20.2+flagos           ✅  empty, 复用 mthreads PyPI 产物
xgrammar:     0.2.5+flagos            ✅  复用 mthreads PyPI 产物
compressed-t: 0.15.0.1+flagos         ✅  复用 mthreads PyPI 产物
vllm_fl:      0.0.0+gd1327ae0a        ✅  纯 Python（无 VLLM_VENDOR）
HCU device:   ✅ 8× 可见               hy-smi (Hygon BW1000)
vllm serve:   ✅ 启动成功              TP=1, enforce-eager, gpu-util 0.85
Inference:    ✅ 成功                  Ministral-8B, 32 tokens
```

### 待办

1. **镜像侧 torch↔numpy ABI** —— ⬜ 阻塞：反馈厂商重编 torch（numpy 2.x），或
   configs.yaml pin numpy 1.26.4
1. **一份 wheel 上传到全部 vendor PyPI** —— ⬜：通用性已实证
   （[§5.2](../decisions.md)），待自动化多厂商上传
1. **更大模型 / TP>1 / yarn rope** —— ⬜：仅测过 Ministral-8B + eager + TP=1

**相关提交：** 无新增代码；复用 [§2.3](mthreads.md) mthreads 的 repack 产物
（PR #280）。
