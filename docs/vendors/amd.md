# amd（AMD / ROCm）

backend key：`amd-rocm7.2.4`。x86_64、python 3.12，单芯片族 `gfx1100`（RDNA3，
Radeon PRO W7900），宿主机驱动 6.16.13。

**状态：只有 base / runtime 层验证过（`rocm-smi` smoke）。** 没有任何 app 层的
`status_matrix.*` 行或 app 页，所以任何「amd 上某 app 通过」的说法目前都是杜撰。

## 平台与设备

- 设备枚举命令 `rocm-smi`（Python 侧走 amdsmi，见下）。
- 设备节点 `/dev/kfd` + `/dev/dri`。
- **`HIP_VISIBLE_DEVICES` 只接受序号或 GPU-UUID**：NVIDIA 风格的 `all` 会解析成空列表，
  于是容器内枚举到 0 张卡、而同一个容器里 `rocm-smi` 却能列出全部卡（自相矛盾的现象）。
  **不设该变量 = 全部可见**。
  （注：flagcx 的 amd builder 仍导 `HIP_VISIBLE_DEVICES=all`，base/runtime 已移除 —— 改
  builder 前先知道这处不一致。）

## 启动容器

- **`--runtime amd` 单独不会注入任何设备节点**：注册在案的 runtime 的 CDI device-manager
  并未接线，`rocm-smi` 会警告 "No AMD GPUs specified"。所以 toolkit 档必须**同时**保留
  显式 `--device` flags。
- raw 档加组要按**组 id**（video），**不能按组名 `render`** —— base 镜像里没有 `render`
  组，按名字加会直接中止启动。
- flags 原文见 `.github/build-config.yml` `run.vendors.amd`。

## 供应商工具链

- **vLLM 的 ROCm 平台探测只认 amdsmi**（`rocm_platform_plugin()` import 失败直接返回
  `None`，没有 `torch.version.hip` 兜底）。base 镜像里带了 ROCm 的 amdsmi 源码树却
  **从不 pip 安装**，而 `amd-smi` CLI 不暴露 Python API → **`amdsmi` 必须是 runtime 的
  pip 依赖**。缺它时平台解析成 `UnspecifiedPlatform`，`create_engine_config()` 报
  `Device string must not be empty`，而 `device_count()` 根本走不到。
- torch 2.11.0+rocm7.2 的 Requires-Dist 是 **`triton-rocm==3.6.0`（不是 `triton`）**；
  FlagTree 的另一个默认后端是 nvidia，所以 amd 的 wheel 构建会连 nvidia 后端一起编，
  需要把 CUDA redists 备好。
- amd 的 flagtree 构建**必须有 LLD**（`find_package(LLD REQUIRED CONFIG)` +
  `lld/Common/Driver.h`），但**不 staging ROCm SDK** —— 后端自带 hip/hsa/roctracer 头，
  运行期靠 `ROCM_PATH`/`hipconfig`/`ldconfig` dlopen `libamdhip64`。
- **`hipsolver-dev` / `hipfft-dev` / `miopen-hip-dev` 是必需的**，尽管 torch 与 vLLM 都不
  link 它们：torch 的头文件在 `USE_ROCM` 下会 include，任何扩展构建（如 flagcx 的 torch
  wheel）缺了就死在 `hipsolver/hipsolver.h: No such file or directory`。
- 本线 `TRITON_BUILD_PROTON=OFF`，所以 `triton.profiler` 不可 import，树里报
  `['amd']`（vendor wheel 是运行期探测的 `['amd','nvidia']`）；与 vendor wheel 做 A/B
  的前提是钉住 `pybind11` internals v11。

## 构建环境的两个坑（镜像构建期，不是运行期）

- **ROCm 从 `repo.radeon.com` apt 直装**（不走 filestore tarball），必须给
  `o=repo.radeon.com` 打 **Pin-600**，否则会和 Ubuntu universe 里更旧的
  `rocm-cmake`/`hipcc`/`rocminfo` 掷骰子。
- 该节点的容器**到不了 `archive.ubuntu.com`**（其 AAAA 记录会挂住），构建要换 aliyun
  镜像并走**明文 HTTP** + `Acquire::ForceIPv4=true`（此时还没有 ca-certificates，
  HTTPS 握手必失败）。
- DKMS 内核驱动**故意不装**（设备由宿主提供）；`amdgpu-core` 在 graphics repo 而不是
  rocm repo。

## 指针

- base / runtime 页（含 Launch 段）：`base/amd-rocm7.2.4.md`、`runtime/amd-rocm7.2.4.md`
- FlagTree amd 线：`packaging/flagtree/README.md`、`packaging/flagtree/amd`
