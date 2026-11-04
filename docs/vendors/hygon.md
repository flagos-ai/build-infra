# hygon（海光）

backend key：`hygon-dtk26.04` / `hygon-dtk26.10`。芯片在代码里叫 **DCU**，SDK 叫 **DTK**，
编译器后端叫 **hcu**（target `gfx936`，warp_size 64）。三套名字都指同一家。

## 平台与设备

- 设备枚举命令 `hy-smi`；**它只在容器内存在，宿主机没有** —— 宿主侧查不到卡不等于
  设备没就绪，必须进容器看（8× HCU，BW1000）。
- `DCU_VISIBLE_DEVICES` **不收窄 torch 的设备视图**（显式设了 torch 仍报 8 张卡），
  要真正固定到某张卡用 `HIP_VISIBLE_DEVICES=<n>`。用前者会静默跑在别的卡上。
- python 3.10（`dtk26.04`）→ wheel 是 cp310，**不能复用 cp312 产物**。

## 启动容器

- **`/dev/kfd` 单独不够，必须 kfd + mkfd 双节点**：mkfd 携带 telemetry，只有 kfd 时
  power/perf 报 N/A、`hy-smi` 报 `Open mkfd failed`。
- `/opt/hyhal` 必须 bind-mount，否则 runtime 看不到加速器。容器 runtime 默认 `dcu`。
- flags 原文见 `.github/build-config.yml` `run.vendors.hygon`。

## 容器内环境

- 与 ascend 同型：base 把 DTK 的 env 抓进 `/etc/profile.d/vendor.sh`，经 `BASH_ENV`
  在**每个非交互 bash**里生效 —— 探测一律走 `bash -c`，`sh`/裸二进制拿到的是空环境
  （DTK 不注册 ldconfig，库路径只由这个 bash-only 的脚本给）。

## 供应商工具链

- DCU 被 torch 以 **CUDA 形态**暴露：`device.type == 'cuda'`、
  `torch.cuda.device_count() == 8`、`flag_gems.runtime.device.name == 'cuda'`。
  **任何「非 CUDA 后端」推理在 hygon 上都是 no-op**，别把 mthreads 那类
  `device.type != "cuda"` 的坑搬过来。
- **DTK 不自带 triton**：默认 `import triton` 落到 flagtree（`/opt/flagtree`）；vendor
  triton 是 build-infra 侧装到 `/opt/triton`（**不在默认 PYTHONPATH**）。所以
  `importlib.metadata` 只看到当前激活的那个，报 absent 属正常。
- torch fork 用 **numpy 1.x C ABI** 编译：镜像若装 numpy 2.x，`tensor.numpy()` 报
  `_ARRAY_API not found` / `Numpy is not available`。矩阵统一 `numpy==1.26.4` 即为此。
  这是**硬约束**（`<2`），不可 fake；opencv 的 `numpy>=2` 是可绕的元数据下限。
- 编译器后端是 **`aillvm`**，由 `llvm_subdir = "aillvm" if rocm_path.name == "dtk"` 选中。
  镜像里没有 DTK 的 LLVM 包时，kernel 编译失败会报**误导性的**
  `HSACOError("File operation failed: ...")` —— 曾据此误判「flagtree 不能编译 hcu kernel」，
  实为镜像缺 LLVM 包，补上后两个编译器都能编。
- **两个 clang 必须并存**：`base/hygon-dtk26.10` 装两个 aillvm 包 —— `dtk_llvm.run` 留下
  clang-18，`dtk_llvm_aicc` 在同一目录上再铺一套 clang-22（`bin/clang -> clang-22`）。
  两条编译器路径各只认一个：vendor triton 3.7.0 传 clang-22 才有的
  `-amdgpu-disable-backoff-barrier=false` / `-fp-fuse=fast` 并产出 clang-22 时代的 IR；
  flagtree 自带 libtriton 的 IR 则只有 clang-18 能解析（`nocreateundeforpoison` 一类属性）。
  只留任一个 clang，F 或 T 必有一条为红。
- flagtree 的 hcu 后端依赖**只有自家 LLVM 树才有**的 HCU MLIR dialect（`ROCDLHCUOps.td` 的
  `mmac_f32_16x16x8f32`、`hcu_matrix_load_32X16_b16` 等）；DTK 的 aillvm 只有 LLVM-IR 层的
  `IntrinsicsHCU.td`，没有这个 dialect —— 所以 flagtree **不能**改用 DTK 的 LLVM 重建，
  clang-18 只能以叠加包的形式保留。
- flagtree 的 hcu 后端曾漏 `kernel.metadata.cluster_dims`，torch 2.9 的 `make_launcher`
  无条件读它 → KV-cache profiling 期 `AttributeError`（flagtree `0.6.2a1+hcu3.6` 已修）。
- DTK 26.10 的 vendor triton 3.7.0 曾有两个**应用层无法绕开**的缺陷（`nvidia` driver
  误判为 active → Triton 被整体禁用；hcu 后端产出 clang-22 时代的 flag/IR 而本机只有
  clang-18）。两者在 `3.7.0+dtk2610.torch2120` 与并存 clang-22 之后都已消失。
  根因与复现见 `packaging/vllm/docs/handoffs/hygon-triton-3.7.0-dtk2610-defects.md`。
  DTK 26.04 的 3.5.1 无 `hcu` 后端，不命中。
- FlagCX 侧：hygon 的适配族名是 **`du`** 而不是 `hygon`（决定 `Provides: libflagcx-<vendor>`）；
  DTK 不导出 `CUDA_PATH`，`DEVICE_HOME`/`CCL_HOME` 必须显式钉；`libnccl.so` 是指向
  `librccl.so.1.0` 的软链，二进制 NEED 的是 `librccl.so.1`。

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/hygon.md`
- FlagCX vendor 事实：`packaging/flagcx/backends.yaml` 的 hygon 两行
