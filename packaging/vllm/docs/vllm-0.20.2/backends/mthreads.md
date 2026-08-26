# vllm 0.20.2 — mthreads musa5.2.0

> 本文对应原报告第 2 部分 §2.3。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.3 mthreads-musa5.2.0（标准流程范例）

**日期:** 2026-08-01/02　**平台:** MTT S5000 (8×, 80GB)　**MUSA:** 5.2.0-server, torch_musa 5.2.0

**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL，`flagos-runtime-mthreads-musa5.2.0:2.1.1`

**这是第 1 部分标准流程的范例来源**——empty 构建、`+flagos` 后缀、单步安装
全部按 §1 执行且无历史包袱。与 MetaX 同为 empty 后端；唯一特殊点：mthreads
的 `torch.device.type` 是 `"musa"`（flag_gems `device_name` 也是 `"musa"`，
所有 GPU 后端中唯一非 `"cuda"` 的），这引出下面的 mul 门控阻塞。

### Repack & Upload —— ✅ 已完成（2026-08-01）

```bash
./packaging/vllm/build-and-repack.sh mthreads-musa5.2.0 --upload
```

一条命令完成：empty 构建 → repack（`+flagos`）→ twine 上传到
`flagos-pypi-mthreads`。上传的包：

| 包 | 版本 | 说明 |
|------|------|------|
| vllm | 0.20.2+flagos | 主包，empty build |
| xgrammar | 0.2.5+flagos | 间接依赖，剥 torch/triton |
| compressed-tensors | 0.15.0.1+flagos | 间接依赖，剥 torch |

关键：`+flagos` 后缀（主包 + 所有递归发现的间接依赖）、A→B→C 依赖链全部
pin 到 `+flagos`（PR #280）。

> **xgrammar 版本说明：** 此处解析到 `0.2.5`，MetaX 记录（[§2.2](metax.md)）
> 当时是 `0.2.3`——两次验证时间不同、上游版本推进所致。同一 vllm 0.20.2
> 今天重跑应解析到一致版本；`repack_recursive()` 按 repack 时的实际依赖树
> 动态决定，不硬编码版本。

### 安装与验证 —— ✅ 已完成（2026-08-02）

按 [§1.4](../playbook.md) 单步安装（`--index-url vendor --extra-index-url
aliyun`，`vllm==0.20.2+flagos`，**不用** `--no-deps`）。131 包依赖树中**零**
torch/triton/nvidia 泄漏：

- `torch` 保持 `2.9.1+musa5.2.0`（未降级），`triton` 不存在
- `flag_gems` 5.3.2 / `flagtree` 0.6.0+mthreads3.6 / `numpy` 2.2.6 全部完好
- `xgrammar`、`compressed-tensors` 解析到各自 `+flagos` 变体
- `vllm-plugin-FL` 安装成功（`0.0.0+gd1327ae0a`，纯 Python，不设
  `VLLM_VENDOR`），`fl` 插件正常激活

**这一结果实证了 [§1.4](../playbook.md) 的单步安装** —— MetaX 曾被迫的两步
`--no-deps` 在 `+flagos` 递归 pin 后不再需要。

> **transformers 不是泄漏源** —— 其 torch 引用全在未激活的 extras
> (`[torch]`/`[all]`/`[dev]`) 之后。早前"transformers 拉 torch"的判断实为
> 未 pin 的 xgrammar bug（PR #280 已修）。

### 阻塞点：flag_gems mul 设备门控回归（由 FlagGems #5130 修复）

`vllm serve` 在模型加载阶段崩溃，命中 rope 的 `1.0 / freqs` 路径：

```none
rope: inv_freq = 1.0 / (base**...)  → Tensor.__rdiv__: reciprocal() * 1.0
 → flag_gems/ops/mul.py  mul_broadcast_func
 → torch.ops.aten.mul.Tensor.redispatch(_FALLBACK_KEYSET, a, 1.0)
RuntimeError: aten::mul.Tensor expected Tensor for 'other', found float 1.0
```

**根因——两步上游回归，并非 kernel bug。** Triton mul kernel 在 MUSA 上
所有路径均正确（实测 scalar/tensor/broadcast/fp16/bf16/int/out=/mul_/complex
误差全为 0）。崩溃纯来自设备门控：

1. **现象：** 所有 mul 在 MUSA 走 fallback，不走优化 Triton 路径

   **根因：** [#4666](https://github.com/flagos-ai/FlagGems/pull/4666) 用
   `device.type != "cuda"` 门控。MetaX 的 torch fork 报 `"cuda"` 故通过；mthreads 报
   `"musa"`（唯一非 "cuda" GPU 后端）被挤出

2. **现象：** fallback 对标量崩溃

   **根因：** [#4999](https://github.com/flagos-ai/FlagGems/pull/4999) 把 fallback 从
   `torch.mul(a,b)`（可处理标量）改成 `aten.mul.Tensor.redispatch(...)`，而
   `mul.Tensor` 要求 `other` 是 Tensor，标量 `1.0` 无法转换

**修复（[#5130](https://github.com/flagos-ai/FlagGems/pull/5130)）：** 门控从
硬编码 `"cuda"` 改为按激活后端设备名判断（符合库自身惯例，如
`_upsample_bilinear2d_aa.py` 用 `input.device.type == device.name`）：

```python
from flag_gems.runtime import device as runtime_device
_DEVICE_NAME = runtime_device.name        # "cuda" / "musa" / ...
...
if device.type != _DEVICE_NAME:           # was: != "cuda"
```

`device_name` 为 `"cuda"` 的后端（nvidia、metax、iluvatar、hygon…）不受
影响；mthreads（`"musa"`）自此走与其他后端相同的优化 Triton 路径。

> **对照 MetaX：** MetaX 没命中此坑，正因其 torch fork 报
> `device.type == "cuda"` 恰好通过门控；mthreads 是唯一暴露该回归的后端。

### serve + 推理 —— ✅ 成功

选 **DeepSeek-R1-0528-Qwen3-8B-FlagOS**（`rope_scaling.rope_type == yarn`）——
正是最直接触发上述崩溃的路径，验证修复最有说服力：

```bash
export MTHREADS_VISIBLE_DEVICES=all
vllm serve /data/DeepSeek-R1-0528-Qwen3-8B-FlagOS --port 8031 \
  --trust-remote-code --max-model-len 4096 --enforce-eager \
  --gpu-memory-utilization 0.85 --tensor-parallel-size 1
# NCCL→MCCL 由 pynccl_wrapper patch 自动完成
```

serve 到达 `Application startup complete`（device_config=musa，MCCL 后端），
全程无 `expected Tensor for 'other'` 报错。

```json
{"choices":[{"text":" a city in the north of France. It is famous for the Eiffel Tower, the Arc de Triomphe",
  "finish_reason":"length"}],
 "usage":{"prompt_tokens":6,"completion_tokens":24,"total_tokens":30}}
```

✅ 修复单独一处即打通整条 serve 路径，本模型无需其他 flag_gems / plugin 改动。

### Stack 验证

```
torch:        2.9.1+musa5.2.0     ✅  from vendor PyPI（未降级）
triton:       (absent)            ✅  MUSA 无 triton，由 flagtree 提供
flagtree:     0.6.0+mthreads3.6   ✅
flag_gems:    5.3.2 + #5130       ✅  mul 门控修复
numpy:        2.2.6               ✅  (Python 3.10)
vllm:         0.20.2+flagos       ✅  empty, repacked, vendor PyPI
vllm_fl:      0.0.0+gd1327ae0a    ✅  纯 Python（无 VLLM_VENDOR）
MUSA device:  ✅ 8× 可见           mthreads-gmi (MTT S5000 8×80GB)
vllm serve:   ✅ 启动成功          TP=1, enforce-eager, gpu-util 0.85
Inference:    ✅ 成功              DeepSeek-R1-0528-Qwen3-8B (yarn), 6→24 tokens
```

### 待办

1. **FlagGems mul 门控 #5130** —— ✅ 已提，E2E 通过：门控改判 `runtime.device.name`；
   merge 后随 flag_gems release 打包进新镜像
1. **repack & upload (+flagos)** —— ✅ 已完成：vllm / xgrammar / compressed-tensors
1. **更大模型 / TP>1 / graph** —— ⬜：仅测过 DeepSeek-8B + eager + TP=1
1. **非 yarn 模型覆盖** —— ⬜：可选，验证更广 rope 路径

**相关提交：** `main` 478de6b（repack）、PR #280（递归 `+flagos` pin）；
FlagGems [#5130](https://github.com/flagos-ai/FlagGems/pull/5130)（mul 门控）

### app image 验证 —— 双后端 F/T 全通（2026-08-24）

这是 vllm 0.20.2 在 mthreads 上的最终交付形态——不再是本节早前的手工容器
安装，而是两个后端各自构建并 push 的 app image（`vllm==0.20.2+flagos` 单步
装入 + `vllm-plugin-fl` wheel + `vllm-serve` launcher），stack 2.1.2：

| 后端 | app image tag | 硬件 |
|------|------|------|
| mthreads-musa4.3.6 | `vllm0.20.2-mthreads-musa4.3.6:2.1.2-0.2.1` | MTT S5000 |
| mthreads-musa5.2.0 | `vllm0.20.2-mthreads-musa5.2.0:2.1.2-0.2.1` | MTT S5000 |

F（FlagTree）/ T（Triton）双路径均 E2E 通过（Qwen3-4B，`--enforce-eager
--max-model-len 2048`），四格全 ✅。

关键包版本：

| 包 | musa4.3.6 | musa5.2.0 |
|------|------|------|
| torch | 2.9.0+musa.4.3.6 | 2.9.1+musa5.2.0 |
| torch_musa | 2.9.0 | 2.9.1 |
| triton | 3.6.0+git89458660 | 3.6.0 |
| flagtree | 0.6.1+mthreads3.6 | 0.6.1+mthreads3.6 |
| flag_gems | 5.3.4 | 5.3.4 |
| numpy | 1.26.4 | 1.26.4 |
| vllm | 0.20.2+flagos | 0.20.2+flagos |
| vllm-plugin-fl | 0.2.1 | 0.2.1 |

三处与前文记录不同：

1. **triton 并非不存在。** 早前 Stack 验证写 `triton: (absent)`，那是
   runtime 2.1.1 的旧状态。2.1.2 起 triton 3.6.0 作为 side install 落在
   `/opt/triton`，不在默认 `PYTHONPATH`（默认是 flagtree）；`compiler
   triton` 切换后即可 import + serve。`importlib.metadata` 只见当前激活
   编译器——app-image 快照比对里 triton 报 `NOT_INSTALLED` 即此故，非缺失。
2. **模型路径。** 节点实际模型在 `/datapool/models/Qwen3-4B`
   （`/data/models` 为空）。
3. **必须带 `--runtime mthreads`。** 不带则 `import vllm_fl` 报
   `0 active drivers`（无设备访问）。

serve 配方（每路径一个端口，先 `compiler <c>` 切编译器）：

```bash
docker run -d --runtime mthreads --env MTHREADS_VISIBLE_DEVICES=2 \
  --network host -v /datapool/models:/datapool/models \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-mthreads-musa5.2.0:2.1.2-0.2.1 \
  sleep infinity
docker exec <容器名> bash -lc "
  compiler triton
  export VLLM_PLUGINS=fl VLLM_FL_DISPATCH_DEBUG=1
  vllm serve /datapool/models/Qwen3-4B --port 8034 --enforce-eager \
    --max-model-len 2048 --gpu-memory-utilization 0.6 --trust-remote-code &
"
```

四条 serve 的 completion 一致输出 "Paris. The capital of Germany is
Berlin..."，health endpoint 均 200。

**mul 门控（#5130）已在镜像内。** flag_gems 5.3.4 自带
[#5130](https://github.com/flagos-ai/FlagGems/pull/5130) 修复，无需再手工
打 patch——早前本节的临时补丁到此收敛为制品。
