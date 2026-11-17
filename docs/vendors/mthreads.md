# mthreads（摩尔线程）

backend key：`mthreads-musa4.3.6` / `mthreads-musa5.2.0` / `mthreads-musa5.3.0`。
芯片 MTT S5000（8×80GB），SDK 叫 MUSA（torch fork 是 `torch_musa`，distributed
后端叫 MCCL）。

## 平台与设备

- 设备枚举命令 `mthreads-gmi`（raw 档把宿主二进制只读挂进容器）。
- 5.3.0 起 python 是 3.12 → cp312（该线只有 cp312 的 vendor wheel）；4.3.6/5.2.0 是
  3.10 → cp310。
- 各 backend 行的 vendor 包**不一样**，各自 PyPI 索引一套 wheel：4.3.6 的 vendor
  triton 是定点构建（`3.6.0+git89458660`），5.2.0 是 `3.6.0`；5.3.0 的编译器发行名
  换成 **`triton-musa`**（`3.6.0+musa5.3.0`），不再是 `triton`。

## 启动容器

- **不起厂商容器 runtime 会得到一个误导性的 `0 active drivers`**：容器起得来，
  `import vllm_fl` 报无设备访问，看起来像插件 bug，其实是 runtime 没给。
- flags 原文见 `.github/build-config.yml` `run.vendors.mthreads`。
- **driver 5.3.0 的节点上，toolkit 档要求宿主 `mtml >= 2.5.0`**：mtml 2.4.2 时
  toolkit（2.1.0）注不进设备 —— 容器起得来却读成没设备，看着像镜像坏了；升到 2.5.0
  后 toolkit 版本不动即可用。**更早的驱动（5.2.0）没有这个要求**，别把下限套到所有行。
  日志里 `Could not locate libmtml_musa.so`、`could not find the major version number`
  在两种 mtml 下都打，是噪声。
- **raw 档（`--device /dev/mtgpu.0 --device /dev/dri`）同样可用**，toolkit 档起不来时
  用 `--run-flags-tier raw`；builder 档的 probe 不用设备，不受影响。

## 供应商工具链（跨厂商结论在此失效）

- **`torch.device.type` 是 `"musa"` —— 本仓里唯一不是 `"cuda"` 的 GPU 后端。**
  硬编码 `device.type != "cuda"` 的门控会静默把 mthreads 排除在优化路径外（flag_gems
  的 mul 门控回归即此，[FlagGems #5130](https://github.com/flagos-ai/FlagGems/pull/5130)
  的修法是改判 `runtime.device.name`）。这类回归只在 mthreads 上暴露。
- **`torch_musa` 是 PrivateUse1，不别名 CUDA**：`torch.cuda.is_available()` 为假、
  硬编码 `device="cuda"` 的 `init_cublas()` 抛 `NotImplementedError`、没有
  `flash_attn_interface`（默认走 `torch_native`/SDPA）。别把别家的「CUDA 别名」结论
  抄过来。
- 没有 NCCL，distributed 后端是 **MCCL**：vLLM 侧由 `pynccl_wrapper` patch 自动换，
  megatron 侧要显式 `--distributed-backend mccl`。
- 编译器后端是 vendor `llc`，target `mtgpu`/`mp_31`；FlagTree 只按目录名认它的 cache，
  不比对版本。
- `importlib.metadata` 只看到当前激活的编译器：观感上的 triton `NOT_INSTALLED`
  是「当前是 flagtree」的意思，不是 triton 缺失。
- **编译器切换在 runtime 2.1.1 上会 `No module named triton.backends.mthreads`**
  （flagtree 装在 `/flagos` 的 site-packages 里没被剥掉）；2.1.2 起移到 `/opt/flagtree`
  已修。**验证用 2.1.2 及以后的 runtime。**
- **5.2.0 的 triton pin 与镜像不一致**：`configs.yaml` 写 `triton==3.6.0`，镜像里实装
  的是 `3.6.0+git89458660`。重跑 runtime 前先对齐。
- FlagCX 侧：mthreads 行链接 `musart` + `mccl`，断言
  `/usr/local/musa/include/{musa_runtime.h,mccl.h}`；vendor 只出 `.deb`。

## 设备状态危险

- **flagtree 0.6.0+mthreads3.6 误编译 `flash_attn_varlen_func`**（`max_abs_diff` 2.94，
  vendor triton 下 0.0055；基本算子都精确）：FlagTree fork 的 mthreads 后端问题，
  走 vendor triton（T 路径）规避，0.6.1 之后未复验。
- flagtree 0.6.0 还把 `base ** freqs` 编成 `fexp2` 的 SIGABRT（0.6.1 已修）。
- **补丁后必须清 `__pycache__`**，否则 serve 读到旧字节码。换插件要
  `pip install -e . --no-build-isolation`，否则 pip 拉公共源 torch 覆盖厂商矩阵。
- fork 后不可重初始化 MUSA：每个 serve 都打一条 `Cannot re-initialize MUSA in forked
  subprocess` —— 只影响 telemetry，**别追它**。

## 指针

- 逐后端记录：`packaging/{vllm,sglang}/docs/*/backends/mthreads.md`
- FlagCX vendor 事实：`packaging/flagcx/backends.yaml` 的 mthreads 行
