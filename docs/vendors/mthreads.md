# mthreads（摩尔线程）

backend key：`mthreads-musa4.3.6` / `mthreads-musa5.2.0` / `mthreads-musa5.3.0`。
芯片 MTT S5000（8×80GB），SDK 叫 MUSA（torch fork 是 `torch_musa`，distributed
后端叫 MCCL）。

## 平台与设备

- 设备枚举命令 `mthreads-gmi`（raw 档把宿主二进制只读挂进容器）。
- python 3.10 → cp310 wheel；5.3.0 起是 3.12 → cp312（该线只有 cp312 的 vendor
  wheel；base 是 24.04，所以系统 python 是 3.12 本身，deadsnakes 只在 22.04 的
  builder 里用）。
- 各 backend 行的 vendor 包**不一样**：各自的 PyPI 索引里一个 SDK 一套 wheel，
  4.3.6 的 vendor triton 是定点构建（`3.6.0+git89458660`），5.2.0 是 `3.6.0`；
  5.3.0 的编译器发行名换成 **`triton-musa`**（`3.6.0+musa5.3.0`），不再是 `triton`。

## 启动容器

- **不带厂商容器 runtime 会得到一个误导性的 `0 active drivers`**：容器起得来，
  `import vllm_fl` 报无设备访问 —— 看起来像插件 bug，其实是 runtime 没给。
- flags 原文见 `.github/build-config.yml` `run.vendors.mthreads`。
- **2026-11-15 起 musa520 节点的 `--runtime mthreads` 整个起不来**：任何带
  `MTHREADS_VISIBLE_DEVICES` 的 `docker run --runtime mthreads` 在 create 阶段失败，
  报 `error discovering devices … error initializing MTML: unknown error: unknown`；
  不带该环境变量则正常。dmesg 给的是 userspace/内核结构体大小错配
  （`[mtvpu] ioctl_mgt_get_info, invalid info size, req:4, size:132, expected:196`）：
  宿主装的 `mtml 2.1.0-linux` 发 132 字节的 info 结构，而 2026-11-14 新装的
  `musa 5.3.0-server` 驱动要 196。**这是宿主 provisioning 问题，不是本仓缺陷**，
  待处置：Nexus `/flagos-pypi` filestore 里有
  `1966bc657_mtml_2.4.2-linux-R_amd64.deb`（包版本 `2.4.2-linux`）可升，
  但动宿主的包要用户拍板，落定后 `docs/vendors/mthreads.md` 与
  `.github/build-config.yml` 两侧都要跟着改。
- 在该缺陷修复前，**raw 档（`--device /dev/mtgpu.0 --device /dev/dri`）可用且枚举正常**
  （`torch.musa.device_count() == 8`）。FlagCX 的 `verify-flagcx-wheel.sh` 用的是
  toolkit 档，所以它在这台节点上跑不完；builder 档的 probe 不用设备，不受影响。

## 供应商工具链（跨厂商结论在此失效）

- **`torch.device.type` 是 `"musa"` —— 本仓里唯一不是 `"cuda"` 的 GPU 后端。**
  任何硬编码 `device.type != "cuda"` 的门控都会静默把 mthreads 排除在优化路径外
  （flag_gems 的 mul 门控回归就是这一条，[FlagGems #5130](https://github.com/flagos-ai/FlagGems/pull/5130) 修法 = 改判
  `runtime.device.name`）。nvidia/metax/iluvatar/hygon 全报 `"cuda"`，所以这类回归只在
  mthreads 上暴露 —— 反过来，**在别的厂商验证通过不代表这条门控是对的**。
- **`torch_musa` 是 PrivateUse1，不别名 CUDA（没有 `gpu_migration` 层）**：所有假定
  CUDA 别名的上游代码都会碎 —— `torch.cuda.is_available()` 为假、硬编码
  `device="cuda"` 的 `init_cublas()` 抛 `NotImplementedError`、没有
  `flash_attn_interface`、默认 fa3 attention 后端需要真的 MUSA flash-attn wheel
  （实际默认走 `torch_native`/SDPA）。**别把别的厂商的「CUDA 别名」结论抄过来。**
- 没有 NCCL，distributed 后端是 **MCCL**：vLLM 侧由 `pynccl_wrapper` patch 自动换，
  megatron 侧要显式 `--distributed-backend mccl`。
- 编译器后端是 vendor `llc`，target `mtgpu`/`mp_31`
  （`/usr/local/musa/bin/llc -march=mtgpu -mcpu=mp_31`）—— 工具链之间真正会变的就是这个二进制，
  而 FlagTree 只按目录名认它的 cache，不比对版本。
- `importlib.metadata` 只看到当前激活的编译器：观感上的 triton `NOT_INSTALLED`
  是「当前是 flagtree」的意思，不是 triton 缺失。
- **编译器切换的坑按 runtime 版本分**：runtime 2.1.1 把 flagtree 装在 `/flagos`
  的 site-packages 里，`compiler triton` 只加 `/opt/triton` 不剥 `/flagos`，于是
  entry_points 收得到 `/flagos` dist-info 的 mthreads 入口、而 `/opt/triton` 里没有
  那个模块 → `No module named triton.backends.mthreads`。2.1.2 起 flagtree 移到
  `/opt/flagtree`（不在 site-packages），切换时两个 side dir 都剥，才修好。
  **验证要在 2.1.2 及以后的 runtime 上做**，在 2.1.1 上炸的 T 路径不代表编译器坏。
- **5.2.0 的 triton pin 与镜像不一致**：`configs.yaml` 写 `triton==3.6.0`，而该后端
  runtime 里实装的是 `3.6.0+git89458660`（那本是 4.3.6 的值）。重跑 runtime 之前先
  对齐，否则 pin 改不动镜像里的东西。
- FlagCX 侧：mthreads 行链接 `musart` + `mccl`，断言
  `/usr/local/musa/include/{musa_runtime.h,mccl.h}`；vendor 只出 `.deb`。

## 设备状态危险

- **flagtree 0.6.0+mthreads3.6 误编译 `flash_attn_varlen_func`**：MTT S5000 上
  `max_abs_diff` 2.94（causal ~4），同镜像 vendor triton 下 0.0055 —— 基本算子
  （add/silu/matmul）两者都精确，逐部件隔离指向 **FlagTree fork 的 mthreads 后端**，
  不在 flag_gems、不在厂商工具链。走 vendor triton（T 路径）规避；0.6.1 之后未复验。
  （enflame 早前看到的 "2.9" 是编译拒绝假象，不是同一回事 —— 该误编译仅 mthreads 一家。）
- flagtree 0.6.0 还会把 `base ** freqs` 路径编成 `fexp2` 的 SIGABRT
  （`LLVM ERROR: Cannot select: v2f32 = fexp2`，0.6.1 已修）。
- **补丁后必须清 `__pycache__`**（`find /opt/vllm-plugin-FL -type d -name __pycache__ -exec rm -rf {} +`），
  否则 serve 读到旧字节码，你会去调一个已经修好的 bug。换插件还要
  `pip install -e . --no-build-isolation`，否则 pip 的隔离环境从公共源拉 torch 覆盖厂商矩阵。
- fork 后不可重初始化 MUSA：vLLM 的 `platform_utils` 会 fork 去查设备属性，
  于是**每个 serve 都会打一条** `Cannot re-initialize MUSA in forked subprocess` ——
  只影响 telemetry，服务本身正常，**别追它**。

## 指针

- 逐后端记录：`packaging/{vllm,sglang}/docs/*/backends/mthreads.md`
- FlagCX vendor 事实：`packaging/flagcx/backends.yaml` 的 mthreads 行
