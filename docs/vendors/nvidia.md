# nvidia（CUDA）

backend key：`nvidia-cuda12.8` / `nvidia-cuda13.3`。x86_64、python 3.12，平台 H20
（megatron 线另有 H100 记录）。**这是唯一 app 层发布名与 backend 名不同的厂商**：
`…-nvidia-cuda12.8` 对外发成 `…-generic-12.8`（同 tag、同内容），按厂商字符串查找
制品路径会落空。

## 平台与设备

- 设备枚举命令 `nvidia-smi`。
- **raw 档只给设备节点不够**：`/dev/nvidia0` + `/dev/nvidiactl` + `/dev/nvidia-uvm`
  之外还要只读挂宿主的三份文件（`nvidia-smi`、`libnvidia-ml.so.1`、`libcuda.so.1`），
  否则容器里既没有 smi 也没有 CUDA。toolkit 档只靠 `--gpus all`，prereq
  `nvidia-container-toolkit`。flags 原文见 `.github/build-config.yml`
  `run.vendors.nvidia`。
- 12.8 与 13.3 都是 python 3.12，**同一个 cp312 wheel 可跨 CUDA 版本用**（12.8 构建的
  wheel 在 cu130 上单步安装即通过）；跨 OS/架构（aarch64）未验。

## 供应商工具链（会污染其他厂商的结论）

- **NVIDIA triton 驱动的 `is_active()` 用 `ctypes.CDLL("libcuda.so.1")` + `cuInit`
  探活 —— 任何带 CUDA 兼容 stub 的平台都会被误判成 active。** 后果是 vLLM 报
  "2 active driver(s) (expected 1)" 后**整体关掉 Triton**，随后首次 kernel 编译
  死在 `_create_driver`。真实案例是 hygon DTK 26.10（`/opt/dtk-26.10/cuda/...` 下有
  stub）；而且**不先 import torch 的探针会看到 `nvidia False`，已加载的进程看到
  `True`** —— 这是"NVIDIA 的代码证伪另一个厂商的 triton 结论"最常见的路径。
- **cp 绑定随线变化**：0.20.2 的 empty wheel 是 `py3-none-any`（到处可复用），0.24.0
  变成 `cp312-cp312-linux_x86_64` —— 仅仅因为声明了 Rust 扩展（`VLLM_USE_RUST_FRONTEND`
  必须保持默认 0），一个 `.so` 都没编也照样把 wheel 绑到 CPython 小版本。→ 每个 python
  小版本各要一份 wheel。
- **CUDA 13.3 上 `import flag_gems` 会因 flagtree 的 nvidia TLE dlopen `libflagcx.so`
  失败**（它 link 的是 `libcudart.so.12`，CUDA 13 没有），而该异常**绕过**
  `has_triton_tle` 的 ImportError 探针 → `deps` 里必须钉 `flagcx==0.14.0+cuda13.3`
  （用它自己的 `libcudart.so.13`），否则回退到 `triton/_C/libflagcx.so` 就复现。
- **flash-attn 的 ABI 锁死 build-time torch == runtime torch**，故按后端打 tag
  （`+fl.cu128.torch210`、`+fl.cu130.torch211`）；它是 RL 动态引擎的硬依赖。
- **插件源码安装必须 `--no-build-isolation`**：构建隔离会自己下载 `torch>=2.7.1`
  （约 2.4 GB）并**用那个 torch 编插件**，直接破坏镜像里匹配好的版本矩阵。
- flagtree 的 nvidia 后端**没有 `register_cache` 钩子**（metax/sunrise/iluvatar 有），
  LLVM 走 `LLVM_SYSPATH`，因此 **`TRITON_OFFLINE_BUILD` 必须保持未设**（一设就要求
  八个 CUDA toolkit 目录 + 一个含 FlagPrism/flagcx 的离线目录）。`LLVM_SYSPATH`
  无人校验，所以 builder 留 hash 记录、wheel 阶段三方比对。
- 空 wheel 的 `_C.abi3.so: undefined symbol: _ZN3c10…` 是**二进制 wheel 与宿主 CUDA
  ABI 不匹配**，非致命（C 扩展优雅降级），但生产要按匹配的 CUDA 源码构建。

## 平台级 kernel / op 地雷

- **零 sgl-kernel / `_Dummy` shim 路线在真 CUDA 上不成立**：CUDA 上 `sgl_kernel` 是默认
  执行路径、有真算子要跑，shim 返回空形状 → 前向崩
  `not enough values to unpack`（qkv 长度 0 / prefill 捕获），CUDA graph 开关都一样。
  这套 shim 在 NPU/PrivateUse1 各厂商成立，**不能搬到 CUDA**。flashinfer 的模块级
  import 里只有 3 处是硬阻塞，其余全被 env/`try-except` 护住。
- **vLLM 0.24.0 的 CUDA 平台无条件 import flashinfer**（`flashinfer_sampler_supported()`
  默认 True）而 runtime 不带 flashinfer → 启动即 import 错。只需 env
  `VLLM_USE_FLASHINFER_SAMPLER=0`。
- **flagtree 路径上硬编码的 `@torch.compile` + torch 2.10 的 inductor 子进程 worker 池
  会崩** `Cannot re-initialize CUDA in forked subprocess`（fork 出的 worker 里调
  `torch.cuda.current_device()`）。规避 `TORCHINDUCTOR_COMPILE_THREADS=1`（强制内联）。
  与其他厂商不同，nvidia 线**没有 jit 补丁前置**，`--disable-jit-fuser` 直接够用。
- **历史更正**：曾把 `opencv-python-headless` 的 `numpy>=2` 当成与 flag_gems
  `numpy==1.26.4` 的真冲突并全局 bump —— 那是**伪冲突**（wheel 编于 2.x 但运行时向后
  兼容 1.x）。真实约束只有 python 版本上限与厂商 torch ABI 两条。

## 设备状态危险

- 本项目内**没有 nvidia 特有的设备占用/毒化记录**。通用的残留容器清理纪律见
  `node-ops` 技能，不在此重复。
- 已知构建期缺口：**cuda13.3 的 runtime 没有 psutil**（12.8 有 7.2.2），声明 psutil 的
  包单步安装会失败，需先走公共镜像预装。

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/nvidia.md`
- 编译链与 repack 口径：`packaging/vllm/docs/vllm-0.24.0/playbook.md`
- 编译器构建事实：`packaging/flagtree/README.md`（nvidia builder 段）
- NVIDIA 驱动 `is_active()` 误认他厂商设备的机制（症状、复现、DTK CUDA stub 的角色，
  以及 hygon wheel 里已落地的改法）：`packaging/vllm/docs/handoffs/hygon-triton-3.7.0-dtk2610-defects.md`
