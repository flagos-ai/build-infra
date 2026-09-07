# sglang 0.5.18 — MetaX maca3.8.1.3 / maca3.7.2.1 验证记录

> **首个 0.5.18 后端**。零 sgl-kernel F/T 双路径 E2E 全过；JIT 缺口 fallback
> 落进交付形态（ADR §5.5）。**2026-09-02 回归**：exp/0.5.18 新插件 wheel
> （sglang_fl-0.2.0rc0，替代旧 0.1.0）重装重验，F/T 双路径全过。同路线第二个
> 后端 maca3.7.2.1 已在 §7 闭环（插件 PR #86 头 a73b27b、5-op yaml
> blacklist，app 镜像 `sglang0.5.18-metax-maca3.7.2.1:2.1.2-0.1.dev1_ga73b27b60`）。

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
| sgl_kernel | sgl-kernel-shim 0.5.18（import 面 shim；发行名 sgl-kernel-shim，模块名 sgl_kernel）|
| sglang-plugin-FL | sglang_fl 0.2.0rc0.post2.dev6+g3a5fc2960（wheel 安装，sha256 3e839424…，构建源 exp/0.5.18 @ 3a5fc29，不含 ascend commit）|
| numpy | 1.26.4（scipy<1.18 guard 后不再漂，app-image 矩阵 unchanged）|
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
  sglang 0.5.18 / sglang_fl 0.2.0rc0 / flag_gems 5.3.5 / sgl-kernel-shim
  0.5.18。
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

> **回归说明**：numpy 曾随 sglang wheel 依赖被 pip 升到 2.3.5（af2e687 实证，
> 当时判「健康」）；后 #706 以 `scipy<1.18` guard 锁死 numpy 1.26.4，app-image
> 矩阵实测 unchanged，不再漂移。completion_tokens=144 是 max cap 而非
> 必然值——Qwen3 默认 thinking 早停，多数请求在 144 前 finish=stop；T 路径
> 第 2 次请求恰好顶满 144（finish=length）。sampling_backend 经 server_args
> dump 确认（0.5.18 chat 响应体无此字段，见 ascend.md 方法论修正）。
> 三个 fallback patch 双路径全良性：0001 clamp_position 优雅回落 eager
> （nvcc: not found，无中断）、0002 vision 未触达（多模态导入忽略）、0003
> fp8 bmm 未成为导入拦路石（仅 fp8 模型路径触达）。

> 性能参考：0.5.12 零 sgl-kernel 同机 ~7-11 tok/s；sgl-kernel 基线 ~40
> tok/s。0.5.18 慢 ~2 倍于 0.5.12，未优化（见 §5 遗留）。

## 4. JIT 缺口 fallback（metax 交付形态，ADR §5.5）

metax torch 是 CUDA-alias，`is_cuda()` True → CUDA 分支被走；无 nvcc →
每个 `load_jit` 优雅失败。三处 fallback 以构建期源码 patch 落进交付 wheel
（`wheels/metax/patches/*.patch`，host 侧应用，见 §3），一处落插件层：

| 文件 | 修复 |
|---|---|
| `patches/0001-clamp-position-fallback.patch` | clamp_position fallback（JIT 失败 → torch-native）|
| `patches/0002-vision-cudnn-guard.patch` | vision.py cudnn guard |
| `patches/0003-fp8-bmm-guard.patch` | fp8_utils bmm_fp8 guard |
| `sglang_fl` PlatformFL | `is_pin_memory_available(self, device=None)` 签名修复（platform.py:318）|

构建期 patch 在 **host 侧**完成：源 tarball 下载、解压、打补丁全部发生在
build 容器启动之前（`build-and-repack.sh` "Pull + patch source" 段），容器只
消费已 patch 的树——`patch` 不是 build image 依赖，改动落在可审计处（用户
约束：不在容器内做 patch）。

## 5. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | 178 文件对 `sgl_kernel` 的 import 面（82 模块级 sym + 29 子模块）| shim 发行名 `sgl-kernel-shim`（模块 `sgl_kernel`，generate.py + `_Dummy` 全能替身）|
| 2 | shim 版本号硬校验 | `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1` |
| 3 | flashinfer import 链（metax 无）| `SGLANG_IS_FLASHINFER_AVAILABLE=false` |
| 4 | F 路径 inductor 并发 fork 崩溃 | `TORCHINDUCTOR_COMPILE_THREADS=1` |
| 5 | CUDA-alias 无 nvcc 的 load_jit 链 | §4 三处 fallback 以构建期 patch 落进 wheel |

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

## 7. maca3.7.2.1（2026-09-07/08；插件 PR #86 头 a73b27b，5-op yaml blacklist）

第二个 metax 后端走 §1–§6 同一条零 sgl-kernel 路线：同一共享
sgl-kernel-shim wheel + 同一批 wheel fallback patch（§4）。E2E 差异在工具链
与 flag_gems 取舍：maca3.7.2.1 的 flag_gems 级联崩溃由插件后端 yaml 逐算子
屏蔽收口（用户定案 blacklist 走插件 yaml、不经 env），两级级联根因见下；
其余依赖差异（flashinfer pin / env 3-key）以 configs.yaml `deps_app` +
`env.app.sglang` 落地（#774 / #781）。

| 项 | maca3.7.2.1（本段）| maca3.8.1.3（§1–§6）|
|---|---|---|
| 镜像 | `flagos-runtime-metax-maca3.7.2.1:2.1.2`（容器内 torch 为准）| 见 §1 |
| torch | 2.8.0+metax3.7.2.0（CUDA-alias，无 nvcc）| 2.10.0+metax3.8.1.0 |
| flagtree（F）| 0.6.1+metax3.6 | 0.6.1+metax3.6 |
| vendor triton（T）| 3.0.0+metax3.7.2.0 | 3.6.0+metax3.8.1.0 |
| flashinfer | runtime 无 → deps_app pin `flashinfer==0.2.6+metax3.7.2.0torch2.8`（#774）| runtime 自带 |
| sglang_fl | `0.1.dev1+ga73b27b60`（exp/0.5.18-metax，PR #86）| `0.2.0rc0.post2.dev6+g3a5fc2960` |
| 模型 | Qwen3-0.6B | Qwen3-0.6B |

> host 驱动读 MACA 3.7.1.5 / kernel 3.3.12 ≠ configs.yaml 的 3.7.2.0 —— 以
> 容器内版本为准（同 §1 原则）。

**flag_gems 级联崩溃根因（两级，5-op blacklist 收口）**：

| 层 | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | serve 首请求崩 `TypeError` | flag_gems Triton 实现覆盖 `_scaled_dot_product_attention_math` 不收 `enable_gqa`；metax vendor sdpa wrapper 的 `(not enable_gqa)` 门把 flash 恒排除（sglang Qwen3 GQA 恒 `enable_gqa=True`）→ builtin 落 math 崩 | blacklist `_scaled_dot_product_attention_math` |
| 2 | 层 1 修复后暴露下一层崩 | native math sdpa fp32 upcast 调 aten::bmm → flag_gems Layer1 覆盖 bmm → fp32 bmm triton kernel 在 flagtree metax 后端编译失败（`PassManager::run failed` / ConvertTritonGPUToLLVM，全 8 autotune 变体）| blacklist `bmm, bmm.out, baddbmm, baddbmm.out` |

**blacklist 5 项**（插件 `metax.yaml` @a73b27b `flagos_blacklist`，英文 why
注释含完整级联链；wheel `0.1.dev1+ga73b27b60` 上传 flagos-pypi-metax）：
`_scaled_dot_product_attention_math, bmm, bmm.out, baddbmm, baddbmm.out`。
命名匹配 flag_gems `GeneralOpRegistrar.config_filter` 按注册 dispatch fn
`__name__` 排除；env `SGLANG_FL_FLAGOS_BLACKLIST` 会整体覆盖 yaml，勿用。
maca3.8.1.3 上这 5 项排除是良性 fallback 非崩溃（该版本未触达层 2），同一
yaml 对本线两版本共用无害。

**E2E（F/T 双路径，Qwen3-0.6B，判据同 §3）**：正式输出 metax123
`/home/secure/metax372-f9-yaml-step7.out`（F9-YAML-EXIT=0）与
`/home/secure/metax372-T-step7.out`（T-EXIT=0）。两腿 serve 均无
`SGLANG_FL_FLAGOS_BLACKLIST` env，serve 日志含 "FlagGems enable (excluding:
['_scaled_dot_product_attention_math','bmm','bmm.out','baddbmm',
'baddbmm.out'])"（来自插件 metax.yaml）。

| 路径 | 编译器 | readiness | 结果 |
|---|---|---|---|
| F | flagtree | ~165s | ✅ 3/3（3× chat/completions 200 / ct=144 / sampling_backend=pytorch）|
| T | vendor triton | ~375s | ✅ 3/3（同上）|

**交付**：configs.yaml `deps_app.sglang0.5.18` maca3.7.2.1 += flashinfer pin
（#774 merged 24ea111；metax 是 CUDA-alias，sampler.py:31 的
`if is_cuda(): from flashinfer.sampling import ...` 在 0.5.18 对 metax 无条件
执行，`SGLANG_IS_FLASHINFER_AVAILABLE=false` 只关 feature 不挡 import）；
`env.app.sglang` 3-key（#781 merged 1a719a5，mirror maca3.8.1.3：
TORCHINDUCTOR_COMPILE_THREADS=1 / SGLANG_IS_FLASHINFER_AVAILABLE=false /
SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1，无 blacklist env——per 用户定案）。
app 镜像 `sglang0.5.18-metax-maca3.7.2.1:2.1.2-0.1.dev1_ga73b27b60` 已发布
（app-image workflow 全 11 步 success，verify 在 metax123 serve E2E 复核；
record PR #783 merged 570d336 已入 status_matrix image_tag）。验证容器与
脚本已净。
