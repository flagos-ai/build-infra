# sunrise（曙光 / TangRT）

backend key：`sunrise-tangrt1.2.0`。芯片 PTPU，SDK 叫 TangRT/tang。python 3.10
（`cp310` wheel），torch 是 `torch-ptpu`。

## 平台与设备

- 设备枚举命令 `pt_smi`；一节点 8 卡（SR-SUN-S2-X1）。
- **没有 toolkit 档**：只有 privileged + 整设备树挂载的 raw 档。因此 **`--device` 换卡被
  显式拒绝**（verify 脚本对 metax/cambricon/sunrise 三家都拒绝 `--device`，而不是静默
  忽略），选卡只能靠 `TANG_VISIBLE_DEVICES`。
- flags 原文见 `.github/build-config.yml` `run.vendors.sunrise`。

## 供应商工具链

- **`torch.cuda.is_available()` 为假**：torch 是 `+cpu` 构建 + PTPU 设备，不是 CUDA 别名。
  别的厂商都以 True 回答、核心提前短路，所以**只被非 CUDA-alias 平台走到的兜底分支
  长期没人跑过** —— sunrise 是第一个把它们撞出来的平台（`get_device` 返回
  `torch.device` 而非字符串；`_DIST_BACKEND_MAP` 无 sunrise 条目 → 默认 `nccl`，
  而该栈只有 `pccl`）。
- **`torch.ptpu` 没有 `memory_stats`**：FL worker 读 `allocated_bytes.all.peak` 时
  引擎初始化直接死（`AttributeError`）。可用 API 只有 `max_memory_allocated` /
  `memory_reserved` / `memory_allocated` / `reset_peak_memory_stats` / `mem_get_info` /
  `empty_cache`，stats 字典只能由插件在 peak API 上合成。
- **`import torch_ptpu` 在没有设备的机器上 abort**（扩展在构造函数里探设备）：
  构建期的 SDK 探针要 dlopen `libpccl.so` / `libtangrt_shared.so` 而不是 import torch；
  构建容器要 privileged 启动（ptpu 平台在 torch import 时无设备即 abort）。
- **flag_gems 必须 ≥ 5.3.6**：5.3.5 在 `enable()` 之前就有两处必崩（`ptpu.libdevice`
  无 `nearbyint`；T 路径无 `asin`），第三处是首个 prefill 的空张量 cumsum 除零 ——
  黑名单够不着。
- **`USE_FLAGTUNE_COST_MODEL=0` 是必需的**：这里的 flagtune 是**旧版本而不是缺失**，
  `triton.flagtune` 能 import 但没有 `runtime/errors.py`，所以 flag_gems cost model 的
  探针**成功**、真正抛出的异常却在回退集合之外 → 任何走到 cost model 的算子直接 abort。
- 编译器构建：**clang-14/lld-14 是正确性要求而不是偏好**（sunrise 后端落在
  clang-only 的 `-Werror -Wno-covered-switch-default` else 分支，gcc 下 `-Werror` 全开，
  `gluon_ir.cc` 报 `-Werror=attributes` —— gcc 产出的是**另一个** wheel，不是响亮失败）。
  pybind11 internals 必须 **v12**（`sunriseTritonPlugin_v0.6.0.4` 的 ABI；metax 的插件是
  v11，方向相反）。
- **RUNPATH 陷阱**：`CMAKE_INSTALL_RPATH` 只作用于 install 期，而 wheel 直接打包
  build-tree 的 `libtriton.so`（不跑 `cmake --install`），必须补
  `-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON`，否则装到 `/opt/flagtree` 后 loader 找不到同目录
  的 `sunriseTritonPlugin.so`。
- flagtree 的 sunrise overlay 会把**测试支持模块带上生产路径**（模块级 `import pytest`
  经 perf-model autotune 路径），所以 `pytest` 是交付依赖（FlagTree #1142，修好后可移除）。

## 平台级 kernel / op 地雷

- **交付黑名单（不是调试残留）**：`_scaled_dot_product_attention_math` **拒绝
  `enable_gqa`**，所有 GQA 模型首个 prefill 即死（非 GQA 调用不受影响，仍走厂商 kernel）；
  `pow_*` 族的 `_fallback_pow` 在本平台 `scalar ** tensor` 失败。
- **探查黑名单是否生效必须先 `flag_gems.enable()`**：只 import 会走原生路径，误判为成功。
- **F/T 双路径必须同一份配置**（env、黑名单、参数），只有编译器不同；两侧配置不一致时
  "双路径通过"这个结论本身不成立。

## 设备状态危险

- **挂死的 kernel 会把卡钉在 100% 且永不退出**，持续到设备/驱动复位或整机重启；
  **`pt_smi -i <n> -r` 清不掉**。历史案例是 FlagTree 旧标签（pre-#978）对
  `flash_varlen_fwd_kernel` 在 decode+GQA 特化下的 codegen 误编译——预填充正常、解码挂死，
  换 stock triton 即正确（因此可以只换编译器完成归因）。#978 后已修复，但**"卡被挂死的
  kernel 占住且软件复位无效"这条平台后果不变**。

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/sunrise.md`
- 编译器构建事实：`packaging/flagtree/README.md`（Sunrise builder 段）
