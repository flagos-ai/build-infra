# sglang 0.5.18 — MetaX maca3.8.1.3 验证记录

> **首个 0.5.18 后端**。零 sgl-kernel F/T 双路径 E2E 全过；JIT 缺口 guard
> 落插件层（ADR §5.5）。**2026-09-02 回归**：exp/0.5.18 新插件 wheel
> （sglang_fl-0.2.0rc0，替代旧 0.1.0）重装重验，F/T 双路径全过。

## 1. 环境

| 项 | 值 |
|---|---|
| 镜像 | `flagos-runtime-metax-maca3.8.1.3:2.1.2`（`-build` 构建 / 本镜像验证）|
| Python | 3.12 |
| torch | 2.10.0+metax3.8.1.0（CUDA-alias：`torch.version.cuda="11.6"`，无 nvcc）|
| flagtree | 0.6.1+metax3.6 @ `/opt/flagtree`（F 路径）|
| vendor triton | 3.6.0+metax3.8.1.0 @ `/opt/triton`（T 路径）|
| flag_gems | 5.3.5（runtime 内置，零 sgl-kernel 路线唯一算子来源）|
| sglang | 0.5.18+flagos（srt_empty 基座 wheel）|
| sgl_kernel | 0.5.18+flagos-shim（import 面 shim）|
| sglang-plugin-FL | sglang_fl 0.2.0rc0.post2.dev6+g3a5fc2960（wheel 安装，sha256 3e839424…，构建源 exp/0.5.18 @ 3a5fc29，不含 ascend commit）|
| numpy | 1.26.4 → 2.3.5（pip 随 sglang wheel 依赖自动升级，唯一依赖偏差；升级后双路径健康）|
| 模型 | Qwen3-0.6B |

## 2. 构建与安装

- 构建：`build-and-repack.sh metax-maca3.8.1.3` 在 `-build` 镜像容器内从
  `sglang-0.5.18.tar.gz`（filestore）构建，`+flagos` repack，上传
  `flagos-pypi-metax`。
- 安装（vendor index + aliyun extra，完整闭包）：

```bash
pip install sglang==0.5.18+flagos \
    --index-url https://resource.flagos.net/repository/flagos-pypi-metax/simple/ \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple/
pip install sglang_fl-0.2.0rc0.post2.dev6+g3a5fc2960-py3-none-any.whl \
    --index-url .../flagos-pypi-metax/simple/ \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple/
```

- `pip show` 三证：direct_url.json 显示 wheel 安装模式（非 editable）；版本
  sglang 0.5.18 / sglang_fl 0.2.0rc0 / flag_gems 5.3.5 / sgl_kernel
  0.5.18+flagos-shim。
- **回归纪律**：旧记录（sglang_fl-0.1.0）不背书新 wheel——本次用 exp/0.5.18
  构建的 0.2.0rc0 重装重验（构建源 @ 3a5fc29 = 4aed74a→eb68346→2d556ac→3a5fc29
  前四 commit，不含 ascend-only commit）。
- 插件激活横幅：

```
sglang_fl platform activating: vendor=metax, device=cuda
PlatformFL initialized: vendor=metax, device=cuda, dist_backend=nccl, count=8
```

## 3. E2E 验证（F/T 双路径，2026-09-02 回归）

服务：`python -m sglang.launch_server`（**顶层模块入口**），Qwen3-0.6B，
`--host 0.0.0.0 --port 30000 --mem-fraction-static 0.6 --trust-remote-code
--disable-cuda-graph --disable-piecewise-cuda-graph`。

判据：HTTP 200 + completion_tokens=144 + sampling_backend=pytorch +
gen tok/s，3× chat/completions。

| 路径 | 编译器 | 结果 | gen tok/s |
|---|---|---|---|
| F | flagtree 0.6.1 @ /opt/flagtree | ✅ 3/3 全过（200/200/200，completion_tokens 85/79/109）| 3.32–4.19 |
| T | vendor triton 3.6.0 @ /opt/triton | ✅ 3/3 全过（200/200/200，77/144/93）| ~3.45–3.55 |

> **回归说明**：numpy 1.26.4→2.3.5 为唯一依赖偏差（pip 随 sglang wheel 自动
> 升级），双路径 import/serve 全健康。completion_tokens=144 是 max cap 而非
> 必然值——Qwen3 默认 thinking 早停，多数请求在 144 前 finish=stop；T 路径
> 第 2 次请求恰好顶满 144（finish=length）。sampling_backend 经 server_args
> dump 确认（0.5.18 chat 响应体无此字段，见 ascend.md 方法论修正）。
> 三处 guard 双路径全良性（wheel-patch 形态实证）：clamp_position 优雅回落
> eager（nvcc: not found，无中断）、vision cudnn 未触达（多模态导入忽略）、
> fp8 bmm 未成为导入拦路石（仅 fp8 模型路径触达）。

> 性能参考：0.5.12 零 sgl-kernel 同机 ~7-11 tok/s；sgl-kernel 基线 ~40
> tok/s。0.5.18 慢 ~2 倍于 0.5.12，未优化（见 §5 遗留）。

## 4. JIT 缺口 guard（metax 交付形态，ADR §5.5）

metax torch 是 CUDA-alias，`is_cuda()` True → CUDA 分支被走；无 nvcc →
每个 `load_jit` 优雅失败；metax flashinfer build 缺 cudnn/bmm 符号。三处
guard 全部落**插件层**（sglang-plugin-FL metax vendor patch，镜像 ascend
`npu_kernel_stubs.py` 先例），sglang 源树保持 pristine 官方 v0.5.18 ——
wheel 构建零 patch：

| guard | 修复 |
|---|---|
| clamp_position | `clamp_position_cuda` 包一层 try/except：JIT 失败 → `torch.clamp(seq_lens-1, min=0)` 回落（forward_batch_info 模块级绑定在插件 patch 之后，取到安全版）|
| vision.py cudnn | 预置 `flashinfer.prefill.cudnn_batch_prefill_with_kv_cache=None`（模块级 bare import 取到 None，不中断 vision.py 导入链）|
| fp8_utils bmm_fp8 | 预置 `flashinfer.bmm_fp8=None`（同上，仅 fp8 模型路径触达）|
| PlatformFL | `is_pin_memory_available(self, device=None)` 签名修复（platform.py:318，exp/0.5.18 主分支）|

patch 在 **load_plugin 时应用**（早于模型模块 import，playbook §6）：插件
wheel 随 app 镜像单步安装，`_apply_vendor_patches()` 按 DeviceDetector
vendor_name 加载 metax patch 模块，模块级 `apply_metax_patches()` 以
setattr/monkey-patch 打进 sglang 内部模块。

> **回归状态**：三 guard 的行为（JIT 优雅回落 / cudnn、bmm 符号缺失不中断
> 导入）在 wheel-patch 形态下双路径 E2E 实证过（§3 回归说明）；插件层形态
> 出包后需按回归纪律重装重验（旧记录不背书新产物）。

## 5. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | 178 文件对 `sgl_kernel` 的 import 面（82 模块级 sym + 29 子模块）| shim 包 `sgl_kernel-0.5.18+flagos-shim`（generate.py + `_Dummy` 全能替身）|
| 2 | shim 版本号硬校验 | `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1` |
| 3 | flashinfer import 链（metax 无）| `SGLANG_IS_FLASHINFER_AVAILABLE=false` |
| 4 | F 路径 inductor 并发 fork 崩溃 | `TORCHINDUCTOR_COMPILE_THREADS=1` |
| 5 | CUDA-alias 无 nvcc 的 load_jit 链 | §4 三处 guard 以插件层 metax patch 落进交付 |

**注意事项：flag_gems SQL ConfigCache 跨编译器污染**（仅 F/T 双路径验证场景
需要处理；最终用户钉单一编译器不触发，无影响）。F/T 同 db 同表
（`/root/.flaggems/config_cache/TunedConfig_metax_triton_3_6.db`）——F 路径
tuning 写 `BLOCK_SIZE_M=8` config 后，T 路径 cache-hit 直接复用 → 硬崩
`PassManager::run failed`。解法：F/T 切换前 `mv .../TunedConfig_*.db
.../.F_backup`，让 T fresh tuning（副作用：T 首 token 慢）。根因链完整证据
闭环见 [metax-0.5.12.md](metax-0.5.12.md)。

## 6. 遗留

- 性能 0.5.18 < 0.5.12（~4 vs ~7-11 tok/s），未优化；sgl-kernel 基线 ~40
  tok/s 差距未追。
- sglang 0.5.16+ circular-import 回归在 0.5.18 metax 实证未触发（其他后端
  仍待 smoke）。
- 验证容器已拆（无保留镜像）。
