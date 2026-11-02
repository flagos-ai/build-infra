# tsingmicro（清微）

backend key：`tsingmicro-tsm260610`。芯片 TX8110（一节点 32 芯片），SDK 叫
TSM Runtime。python 3.10，torch 是 `torch-txda`（PrivateUse1）。

## 平台与设备

- 设备枚举命令 `tsm_smi`；设备节点 **`/dev/accel` + `/dev/accel_drv_mgr` 两个都必需**
  —— 只给一个时 `torch_txda` 在 import 期就 abort。
- toolkit 档靠厂商容器 runtime + `TSINGMICRO_VISIBLE_DEVICES`，prereq
  `tx-container-toolkit >= 2.5.0`；flags 原文见 `.github/build-config.yml`
  `run.vendors.tsingmicro`。

## 供应商工具链

- **`torch_txda` 在无设备的机器上 import 不可**（`TXDAHooks` 构造函数探
  `txGetDeviceCount` 并 abort）；构建期的 SDK 探针要用 `txops`（它只 CDLL
  `libtxdnn` + import pytxdnn，不探设备）。
- **flagtree-tsingmicro 的 wheel 永远无法在 docker build 里做 import smoke**
  （`third_party/tsingmicro/backend/driver.py` 模块级 import `torch_txda`，而 build
  拿不到 `/dev/accel`）。这是唯一没有 import smoke 的 builder —— 它改为断言 wheel
  内容，因为 `install_extension` 对缺失的 CMake 产物只 warn，否则缺 `tsingmicro-opt`
  的 wheel 会被放过并发布。
- **不要用 `triton.__version__` 认编译器身份**：同一个 FlagTree 厂商 pin，运行时自报
  过 3.3.0 也自报过 3.6.0。
- 暂存的 clang 必须通过 PATH 走 cmake（镜像里**没有** apt clang）：
  `FlagTreeOptions.cmake` 按裸名找 `clang`/`clang++`，crt/profiler 则走
  `${LLVM_SYSPATH}/bin/clang` 绝对路径。两套预置树（`tsingmicro-llvm22`、`tx8_deps`）
  按目录名匹配，必须 `--strip-components=1` 解到精确的 cache key。
- **`libfmt.so.8` 只能来自 Ubuntu 22.04**（`torch_txda` link 的是 `.so.8`，24.04 只有
  `.so.9`），以 dpkg 安装，且**不是** SDK 组件。
- base 镜像烘入 `USE_TORCH_XLA=0`、`TORCH_COMPILE_DISABLE=1` 与
  `KUIPER_PATH`/`TX8_DEPS_ROOT`/`LLVM_SYSPATH`/`LLVM_BINARY_DIR`。

## 平台级 kernel / op 地雷

- **flag_gems 的 attention 内核在 TX8110 上静默算错**（`flash_attn_varlen_func` 实测
  `maxrel=inf/nan/37.7`），`rms_norm` / `rotary_embedding` 同样算错（`maxrel~7200`）。
  **`strict: false` 救不了**：它只在**抛异常**时回退，算错不抛。→ attention 用 torch
  SDPA 计算、KV 用基础索引写入，这两个才数值正确。
- **triton copy 内核在改 dtype 的 cast 上挂死**（采样阶段 int32→int64）→ 黑名单
  `to_copy` / `copy` / `copy_` / `masked_fill`。
- **native 回退不安全，不能当作兜底**：`gather` 走 native 时进程无 traceback 静默崩溃
  （TXML segfault），native `sort` / `gather` / `lt` 也极慢。所以黑名单**只应含 copy 族
  + `masked_fill_`**，不能为了绕一个算子把 `sort` / `gather` / `softmax` 一起黑掉 ——
  那等于把采样热路径推给 native。
- **list 索引没有 PrivateUse1 kernel**：`key_cache[blocks]` 回退 CPU 并把**整个 cache**
  拷一遍 → 引擎级挂死（不是报错）。改 per-block slice + cat。
- **tensor-index 赋值写 paged KV cache 要绕主机内存一圈**：284 MiB cache 上写 1 行与
  写 2048 行同价（各约 166 ms），每个 decode step 因此多出数秒；`cache[block_id,
  offset] = row` 约 0.02 ms。
- **0-dim `Tensor.item()` 必崩**（`RuntimeError: TXDA error: (txMemcpyAsync(...)) =
  Invalid parameters`），改用 `.tolist()`（0-dim 亦可）。
- **strided 设备张量读慢 ~80 倍**（223.74 ms vs 2.75 ms）；`torch.chunk(2, dim=-1)`
  产出的正是这种 view（每层约 220 ms × 36 层），cos/sin 两半要一次 `.contiguous()`
  物化并缓存。
- **profile 期 `slot_mapping == -1` 会写进最后一个 block**（`-1 // block_size == -1`）
  —— 静默写穿，必须加 `slot >= 0` guard。block table 行被 padding 到
  `max_model_len / block_size`，padded 项仍付设备 op，要按真实块数截断。
- 分布式后端必须映射 `txda → tccl`。

## 设备状态危险

- **SIGKILL 一个持有 txda 上下文的进程会把设备卡在低功耗态**（`import torch_txda`
  报 `Failed to discovery devices` / `1124073480`，`tsm_smi` 仍显示全部 Online、
  心跳正常、PCI D0 —— 表面健康）。容器重启不解决，驱动层状态跨容器。
  **恢复 = 驱动级 reset（FLR / unbind+rebind / 用户重置驱动），属节点级操作，须先获授权。**
  调试期停 serve 一律优雅停（先 APIServer 再 EngineCore），别 SIGKILL。
- **一张 TX8110 只有一个 compute 上下文**：被卡死进程占住后任何提交都被拒
  （`failed to submit ... compute job: -110`，内部重试表现为 CPU 100% 假旋转）。
  **同一时刻绝不要有两个进程碰同一张卡。**
- **`docker restart` 会 SIGKILL 占用进程** → 触发上面第一条，两者叠加后只剩驱动级
  reset 一条路。宿主驱动模块缺失时（重启后 KMD 没装）`docker run` 报
  `tx-container-runtime did not terminate successfully` —— 这是**驱动没装，不是设备故障**，
  别当毒化处理；重装驱动后 `tsm_smi` 回到 32 芯片、容器内 `device_count()` 回到 32。
- **窗口化 serve（`--hf-overrides '{"sliding_window": N}'`）在本平台必挂**：READY 后约 30 s
  触发 `action=RESET_BM`，计算上下文被打掉、请求全超时；**换回修复前的 attention.py 同样触发**，
  故这是窗口路径本身的问题，不是任何 mask 代码引入的。stock 配置（`sliding_window=null`）不受影响。
- 冷启动 JIT 让**两条编译器路径的首个请求都超过 300 s 客户端超时**（warm 后正常）。
  定长超时的验证脚本会把它算成失败。T 路径还要再慢约 40%，排验证时间要按此估。

## 指针

- 逐后端记录：`packaging/vllm/docs/*/backends/tsingmicro.md`
- 编译器构建事实：`packaging/flagtree/README.md`（Tsingmicro builder 段）
- SDK 探针用法：`packaging/flagcx/README.md`
