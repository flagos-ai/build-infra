# MetaX maca3.8.1.3 — sglang 0.5.12 零 sgl-kernel 参考记录

> 0.5.18 方案的前身实证（2026-08-28）：零 sgl-kernel 路线可行性闭环 + 完整根因链。
> 0.5.18 正式记录见 [metax.md](metax.md)；已落进交付形态的处置（shim / flashinfer
> 开关 / inductor 线程钉 1）以 0.5.18 记录为准，本文保留根因链参考价值。

## 背景与目标

按"零 sgl-kernel 可行性定案"（`zero-sgl-kernel-feasibility-20260828.md`）的技术路线，
在 metax maca3.8.1.3 后端把 sglang 0.5.12 从零跑通，不装 sgl-kernel，全部算子走
flag_gems。记录从零搭建中遇到的全部坑点与解法。sglang 版本选择：torch 2.10.0 取最高
可用 0.5.12（0.5.16 有 circular-import regression，排除）。

## 结论摘要

**F（flagtree）/ T（vendor triton）双路径 E2E 全过**，零 sgl-kernel 路线在 metax 后端
成立。Qwen3-0.6B chat/completions 3 连发全过，completion_tokens=132，采样 backend 落
pytorch。性能约 7-11 tok/s（基线 sgl-kernel 路径约 40 tok/s，慢 4-5 倍，为后续优化项）。

## 环境

| 项 | 值 |
|---|---|
| 镜像 | flagos-runtime-metax-maca3.8.1.3:2.1.2 |
| 设备 | MetaX C550，capability (8,0)，shared mem 64KB 上限 |
| torch | 2.10.0+metax3.8.1.0（CUDA-alias，is_cuda()=True） |
| triton（vendor） | 3.6.0+metax3.8.1.0（/opt/triton） |
| flagtree | 0.6.1+metax3.6（/flagos 默认） |
| flag_gems | 5.3.5 |
| python | 3.12 |
| 模型 | Qwen3-0.6B（/data/models/Qwen/Qwen3-0.6B，容器内直读） |
| 启动参数 | --mem-fraction-static 0.6 --trust-remote-code --disable-cuda-graph --disable-piecewise-cuda-graph |

Qwen3-0.6B 关键形状：head_dim=128、hidden=1024、intermediate=3072、num_heads=16、
num_kv_heads=8 → qkv_proj N=(16+8+8)×128=4096、K=1024，是崩溃 config 的命中形状。

## 坑清单

### 1. sgl_kernel import 面 → shim 包

0.5.12 有 12 个文件的模块级无条件 `import sgl_kernel`（CUDA/NPU 专用路径）。不装
sgl-kernel 时这些 import 直接失败。解法：装一个 sgl_kernel shim 包（空模块）满足 import
面，运行时全部走 flag_gems / 平台守卫分支，shim 的符号不会被真正调用。

### 2. torch.library.register_fake → register_fake_if_exists

部分路径在 import 期对 sgl_kernel 的算子注册 `torch.library.register_fake`（fake tensor
规则），shim 提供不了。解法：patch_torch.py:116 用 `register_fake_if_exists` 包裹，规则
不存在时跳过，不再硬崩。

### 3. flashinfer 崩溃 → SGLANG_IS_FLASHINFER_AVAILABLE=false

flashinfer 采样 JIT 与 fp4_quantization 路径在 metax 崩溃。解法：环境变量置 false 禁用，
采样 backend 落 pytorch（get_server_info 实证 sampling_backend=pytorch），功能不受影响。

### 4. F 路径 inductor fork 崩溃 → TORCHINDUCTOR_COMPILE_THREADS=1

flagtree 编译器下 inductor 多线程 fork 崩溃。解法：编译线程数钉 1。

### 5. T 路径 vendor triton MMA M-tile=8 限制（厂商侧）

vendor triton-3.6.0+metax3.8.1.0 的 bf16 MMA 断言 `shape_judge && "tn and tk not meet
conditon"`：BLOCK_SIZE_M=8 的 GEMM tile 编译失败，M-tile≥16 全过（raw kernel 14 组合
实证）。flagtree 无此限制。处置：vendor triton 侧缺陷，移交厂商。

## 注意事项：flag_gems SQL ConfigCache 跨编译器污染

> 仅 F/T 双路径验证场景需要处理；最终用户钉一个编译器不触发，无影响。

### 现象

F 路径 serve + E2E 全过后，T 路径（PYTHONPATH=/opt/triton）serve 在首个请求直接硬崩
`RuntimeError: PassManager::run failed`，触发位置 libentry.py:1085
`self.fn.run(*args, **kwargs, **config.all_kwargs())`。直接调 fg_ops.linear（M=8/16/32、
N=3072）却全 OK，矛盾。

### 根因链（证据闭环）

1. flag_gems 5.3.5 的 LibCache（libentry.py:280）持久化到 SQLite：
   `config_cache_dir()/TunedConfig_{vendor}_triton_{major}_{minor}.db`（可用
   FLAGGEMS_DB_URL 覆盖）。文件名只含 vendor + triton 主次版本号 → flagtree 3.6.0 与
   vendor triton 3.6.0 共享同一文件
   `/root/.flaggems/config_cache/TunedConfig_metax_triton_3_6.db`。
2. SQL 表名 = `{name}_{kernel_hash}-{md5(列名)}`（libentry.py:526 + sql.py
   get_sql_model），kernel_hash = md5(cache_key + configs_hash)（libentry.py:632）。
   cache_key 与 configs_hash 均与编译器身份无关 → F/T 计算出完全相同的表名 → 同一 SQL
   表 → 跨编译器共享是结构性必然，非偶然。
3. F 路径（flagtree）可编译 M-tile=8，bench 选出 (8,4096,1024)→(8,32,32,num_warps=4)
   （0.0259ms 最快）写入 Config 表。
4. T 路径 serve 的形状 (8,4096,1024)（Qwen3-0.6B qkv_proj）命中 cache-hit 分支（DBG
   无 "run configs len=" 打印实证）→ 直接取 (8,32,32) → vendor triton MMA M-tile=8
   编译失败 → 硬崩。
5. 关键：cache-hit 分支（libentry.py:1085）在 bench() 的 `except RuntimeError → inf`
   保护（libentry.py:998 注释点名 cambricon "PassManager::run failed"）之外 → 编译失败
   直接炸，不会降级重选 config。

### 解法与验证

移走缓存 db（`mv TunedConfig_metax_triton_3_6.db .bak`）→ T 路径 fresh tuning →
bench() 把 M-tile=8 全部标 inf（p50=inf 实证）→ 崩溃形状重选 (32,64,32,num_warps=2,
num_stages=5)（安全）→ T 路径 serve + E2E 全过（9.5/11.0/6.9 tok/s）。修复前 db 中
(8,4096,1024)/(8,6144,1024) 的 config 均为 (8,32,32,4,1,4)；修复后为
(32,64,32,2,1,5)，表名不变（`6e3c9826...-0f015d35...`）—— 结构性共享的又一实证。

### 处置

- flag_gems：cache key / 表名应含编译器身份（或同 db 分表），或 cache-hit 路径加编译
  保护（M-tile=8 编译失败时重选）。移交 FlagGems 修复。
- vendor triton：metax M-tile=8 bf16 MMA 编译失败（M≥16 全过），移交厂商。
- 运维侧：同一后端换编译器（F/T 切换）前清 flag_gems 调优缓存，或全程钉一个编译器。

## 遗留

- 性能：零 sgl-kernel 路径 7-11 tok/s vs 基线 ~40 tok/s，慢 4-5 倍，未优化（0.5.18
  同机 ~4 tok/s，见 [metax.md](metax.md) §6）。
- 验证容器已拆；模型权重在节点 /data/models/Qwen/Qwen3-0.6B，容器创建时映射即可用。
