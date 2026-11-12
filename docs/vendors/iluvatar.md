# iluvatar（天数智芯）

backend key：`iluvatar-corex4.5.0` / `iluvatar-corex5.0.1`。芯片 BI-V150，SDK 叫 CoreX，
工具链根 `/usr/local/corex`，FlagTree/triton 后端名 **`IX`**，编译器是 **corex clang**。

> `iluvatar-corex4.4.0` 自 FlagOS 2.3.0 起退役，由 `corex5.0.1` 接替。下文仍保留若干
> 4.4.0 的历史细节（triton 3.1.0 误编译、仅 F 交付等），待 5.0.1 on-node 验证后随
> app/verify PR 一并改写；5.0.1 的 F/T 交付形态在验证前不臆测。

## 平台与设备

- 设备枚举命令 `ixsmi`；设备节点 **`/dev/iluvatar0` + `/dev/itrctl` 两个**（只给卡节点
  会漏掉控制设备）。
- **设备报 `cuda`**：torch 是 CUDA 别名构建，`torch.cuda.get_device_capability()` 返回
  **`(7, 1)`** —— 这是 CoreX 的兼容标签，**不是 NVIDIA SM 等级**，别喂给任何按 SM 分支的逻辑
  （sglang 侧就是被它触发了强制 fp16 + "sm75 only"）。`device="xpu"` 会报
  `Torch not compiled with XPU enabled`。
- 现役两条线：4.5.0 锁 **torch 2.10.0**，5.0.1 锁 **torch 2.13.0**；flagtree 同为
  `0.7.1a1+iluvatar3.6`，triton 分别是 `3.2.0+corex.4.5.0` 与 `3.6.0+corex.5.0.1`。
  （已退役的 4.4.0 曾锁 torch 2.7.1，低于 "torch ≥ 2.8" 的 API 下限，故当时需 torch-compat-shim。）
- 节点任务只能由有 docker 权限的账号跑（这个厂商的验证节点上只有一个账号有权限）；
  **卡 0 留给镜像构建**，验证用 `IX_VISIBLE_DEVICES=<n>` 换卡。看不到设备 / docker 被拒
  是账号问题，不是镜像缺陷。具体是哪台机、哪个账号见 `scripts/verify-nodes.local.yaml`
  （git-ignored）。

## 启动容器

- toolkit 档靠厂商容器 runtime + `IX_VISIBLE_DEVICES`，**不是 `--device` 列表**；
  prereq `ix-container-toolkit >= 1.1.0`。
- 驱动用户态（`libcuda.so.1`、`libixml.so`、`ixsmi`）装在**镜像里**，不从宿主挂载
  （内核模块在容器里加载不了，留在宿主）—— 按宿主挂载的思路搭环境在这个厂商是错的。
- flags 原文见 `.github/build-config.yml` `run.vendors.iluvatar`。

## 供应商工具链

- **vendor corex triton 3.1.0（SDK 4.4.0）有不可修复的误编译**：它把 flag_gems **自己的**
  kernel 编成错值，所有 Triton attention/sampler 路径输出乱码；插件层与镜像层都无解，
  只能升厂商 SDK。故 4.4.0 的交付形态是 **只有 F（FlagTree），T 不交付**。
  **corex 4.5.0 的 triton 3.2.0 没有这个缺陷**，同一 T 路径直接通过。
  ⚠️ 别把它推广成「4.4.0 的 triton 不可用」—— sglang 在同一个 4.4.0 上 T 路径是过的，
  因为那边失败的是注入的 no-op 而不是厂商编译器。
- triton **3.1 严格、3.2 宽松**：3.1 的依赖遍历会 assert
  （`Function "_noop" is being called from a Triton function but is not a Triton function itself`），
  3.2 只 warn —— 注入辅助可调用对象的插件在 4.5.0 能用、在 4.4.0 会炸。
- triton 3.2 **没有 PDL intrinsic**（`tl.extra.cuda.gdc_launch_dependents`），且它的 JIT 在
  AST 预扫阶段解析函数体里**所有**属性 → `USE_PDL=False` 的分支照样编译失败。
- 需要绕开的是**vLLM 上游原生 Triton kernel**（混合符号 `uint32 // int32`、PEP 526 注解赋值），
  **flag_gems 自己的 kernel 在 corex 上编得过** —— 与直觉相反。
- **确定性由编译器决定，不由 kernel 源码决定**：同一个 flag_gems GEMM kernel，FlagTree 在
  活动引擎里编出来逐次不确定（~1-2 bf16 ulp），vendor corex triton 编出来 bitwise 确定；
  原生 corex **ixblas** 既确定又更快。要确定性得把整个 GEMM 族拉黑
  （只黑 `linear` 不够，native linear 会退化成 addmore 仍被劫持）。
- **不要设 `CPATH`**：corex clang 自己会搜 `/usr/local/corex/include`，多加一条 CUDA 10.2 的
  头文件路径会遮蔽 corex 自己的 `cuda.h`，运行期编译报 `cuda.h did not define IX_VERSION`，
  所有 Jiterator 算子全灭。
- **两条线都没有可用的 nvcc-JIT**：4.5.0 根本没有 nvcc；4.4.0 有 nvcc 10.2 但 JIT 构建失败
  （`cannot find cuda_0.o`）。所以「nvcc 编得过 ⇒ 能用」这个判据在此平台**必然假阳性**。
- flagtree iluvatar overlay 会把一个**测试支持模块带上生产路径**
  （`triton/spec/iluvatar/.../testing.py::nvsmi` → 模块级 `import pytest`），所以生产镜像
  必须装 `pytest`；vendor triton 在同函数里本地定义 `is_corex()`、不碰它
  （属 flagtree spec-overlay 的打包缺陷，不是调用方问题）。

## 硬件能力

- **bf16 的支持随 app 路径而变**：sglang 记录 BI-V150 无 bfloat16（dtype 必须降到 fp16，
  且要摘掉 NVIDIA 的 sm80 下限，因为 capability (7,1) 会触发它），而 vllm 线在同一块板上
  `--dtype bfloat16` 能跑。**依赖 bf16 前先实测，别从另一条 app 线搬结论。**

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/iluvatar.md`
- 编译器构建事实：`packaging/flagtree/README.md`（Iluvatar builder 段）
