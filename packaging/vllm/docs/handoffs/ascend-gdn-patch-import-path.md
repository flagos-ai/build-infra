# vllm-plugin-FL Ascend GDN Patch — 模块路径失效（vllm 0.24.0 重构）

## Status

**根因已定位，修复已验证。** vllm-plugin-fl 0.3.0 的 Ascend GDN patch 引用了
vllm 重构前的旧模块路径 `mamba.gdn_linear_attn`，导致所有 GDN patch 在
try/except 中静默失败（no-op），混合架构模型（Qwen3-Next 等 GDN/hybrid 模型）
输出异常。plain-attention 模型不受影响。

**日期：** 2026-10
**平台：** Ascend 910C，CANN 9.0.0，torch_npu 2.10.0
**镜像：** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-ascend-cann9.0.0-910c:2.2.0-0.3.0`
**插件：** vllm-plugin-fl 0.3.0

---

## 1. 症状

vllm serve 启动时日志出现（良性警告外观，实际为功能缺失）：

```
No module named 'vllm.model_executor.layers.mamba.gdn_linear_attn'
```

此警告出现 5 次，对应 `ascend/patch.py` 中 5 处 GDN 相关 import。由于所有
import 包裹在 `try/except`，patch 静默跳过，GDN 层未被 Ascend 后端接管 →
混合架构模型输出乱码或异常。

## 2. 根因

vllm 0.24.0 将单文件 `vllm/model_executor/layers/mamba/gdn_linear_attn.py`
重构为包目录：

```
vllm/model_executor/layers/mamba/gdn/
    __init__.py                  (空，无 re-export)
    base.py
    qwen_gdn_linear_attn.py
    kimi_gdn_linear_attn.py
    olmo_gdn_linear_attn.py
```

但 `vllm_fl/dispatch/backends/vendor/ascend/patch.py` 的 5 处 import 仍引用旧路径：

| 行号 | 原始 import |
|---|---|
| ~131 | `import vllm.model_executor.layers.mamba.gdn_linear_attn as _gdn_lib` |
| ~148 | `import vllm.model_executor.layers.mamba.gdn_linear_attn as gdn_lib` |
| ~253 | `import vllm.model_executor.layers.mamba.gdn_linear_attn as _gdn_lib` |
| ~425 | `import vllm.model_executor.layers.mamba.gdn_linear_attn as _gdn_lib` |
| ~613 | `import vllm.model_executor.layers.mamba.gdn_linear_attn as _gdn` |

## 3. 修复方案

将单一旧路径替换为多路径列表，逐一尝试加载所有 GDN 子模块：

```python
_GDN_MODULE_PATHS = [
    "vllm.model_executor.layers.mamba.gdn.qwen_gdn_linear_attn",
    "vllm.model_executor.layers.mamba.gdn.kimi_gdn_linear_attn",
    "vllm.model_executor.layers.mamba.gdn.olmo_gdn_linear_attn",
]

def _load_all_gdn_modules():
    mods = []
    for path in _GDN_MODULE_PATHS:
        try:
            mods.append(importlib.import_module(path))
        except ModuleNotFoundError:
            pass
    return mods
```

每处原来的 `import ... as _gdn_lib` 改为调用 `_load_all_gdn_modules()` 并对
返回的 module 列表逐一 patch。

**验证**：修复后 vllm serve Qwen3.5-4B（GDN/hybrid 模型）启动不再报 GDN
import 警告，GDN 层正确由 Ascend 后端接管，输出正常。

## 4. 影响范围

- **受影响**：所有使用 GDN/hybrid 架构的模型（Qwen3-Next 等），在 Ascend 后端 +
  vllm 0.24.0 + vllm-plugin-fl 引用旧路径时
- **不受影响**：plain-attention 模型（Qwen3、Qwen2、Llama 等）—— 不走 GDN
  patch 路径
- **其他后端**：metax 的 `metax/patches/gdn_linear_attn.py` 也引用旧路径
  （有 try/except fallback）；GCU 的 `gcu/impl/fused_recurrent_packed_decode.py`
  同样引用旧路径。修复逻辑相同，但需各后端各自适配

## 5. 归属

- **缺陷归属**：vllm-plugin-FL 的 `dispatch/backends/vendor/ascend/patch.py`，
  未跟进 vllm 0.24.0 的模块重构
- **修复归属**：vllm-plugin-FL（需在各后端的 patch.py 中更新 import 路径）
- **build-infra 侧**：无需额外 patch 机制；修复合入 vllm-plugin-FL 后，下次
  构建 app 镜像时 wheel 自然携带修复

## 6. 已有文档引用

- `packaging/vllm/docs/vllm-0.24.0/backends/ascend.md` §10.2：
  "GDN/hybrid 模型（Qwen3-Next）0.24.0 暂不支持：0.24.0 把
  `mamba/gdn_linear_attn.py` 重构为 `mamba/gdn/` 包，patch.py 的 GDN
  补丁目标符号失效（try/except 静默 no-op）。"

## 7. 复现

```bash
# 在 ascend 910C 容器内
python3 -c "import vllm.model_executor.layers.mamba.gdn_linear_attn"
# → ModuleNotFoundError: No module named 'vllm.model_executor.layers.mamba.gdn_linear_attn'

python3 -c "import vllm.model_executor.layers.mamba.gdn.qwen_gdn_linear_attn; print('OK')"
# → OK
```
