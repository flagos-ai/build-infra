# cambricon（寒武纪）

backend key：`cambricon-neuware4.4.3` / `cambricon-neuware4.7.2`。芯片 MLU590，SDK 叫 Neuware。

**本厂商没有 FlagTree**：`configs.yaml` 两行都没有 `flagtree:` 键，F 路径不存在，矩阵里
F 列是「—」，**只有 T 会被验证**。看到 cambricon 的格只有 T 通过不是缺测。

## 平台与设备

- 设备枚举命令 `cnmon`；设备节点 **`/dev/cambricon_dev0` + `/dev/cambricon_ctl`**。
- **没有容器 toolkit / runtime**，raw `--device` 直挂是唯一启动方式。
- **4.4.3 起必须直挂设备节点**：`MLU_VISIBLE_DEVICES=N` 的 env 形态下设备不可见、进程提前
  退出 —— 4.4.3 上「找不到设备」是**启动方式问题**，不是驱动问题。
- 4.4.3 的 base 镜像锁 Ubuntu **22.04**（`cnperf` 需要 `libncurses5`，24.04 已移除）；
  4.7.2 走 24.04。python 也不同（4.4.3 = 3.10，4.7.2 = 3.12），**wheel 不可复用**。
- flags 原文见 `.github/build-config.yml` `run.vendors.cambricon`。

## 供应商工具链

- **PrivateUse1，不是 CUDA 别名**：`torch_mlu` 注册自己的 `mlu` 设备类型，
  `torch.cuda.is_available()` 为 **False**，张量是 `torch.mlu.BFloat16Tensor`。
  **与 iluvatar/kunlunxin 的失败形态正好相反** —— 那边一切 `is_cuda()` 分支被误触发，
  这边一切 `torch.cuda.is_available()` 断言直接挂。给一边打的补丁在另一边是错的。
- **CUDA 迁移门面不完整且会说谎**：`get_device_capability()` 报 **(5, 0)**（假值，sglang 据此
  判成 legacy sm50 并强制 fp16 + "sm75 only"，需伪装成 (8,0)）；缺
  `_MLUDeviceProperties.is_integrated`；`torch.Stream` 是包装而不是类，`isinstance` 检查失败。
- `device_name()` 报 `'cuda'` 而张量 `device.type == 'mlu'` → 优化器报
  `TypeError: Wrapped parameters must be one of accelerator ... Received torch.mlu.BFloat16Tensor`。
  megatron 的平台注册表**没有 mlu 项**，靠 gpu_migration 桥接选中 CUDA。
- vendor triton：`3.2.0+mlu1.7.2`（4.4.3）/ `3.4.0+mlu2.1.1`（4.7.2）。**同一 SDK 线的启动
  kwarg 也不同**：flag_gems 5.3.5 的 cambricon 后端发 `task_type='block'`，3.2.0 会拒。
- `torch.mlu.MLUGraph` **存在**（等价 CUDAGraph），图捕获可用。
- `torch.library.get_kernel()`（flag_gems 5.3.5 用）只在 torch ≥ 2.8 有，
  `float4_e2m1fn_x2` 只在 CUDA torch 2.7+ 有 —— 本厂商 2.7.1+cpu 树两者都没有，需要兼容垫片。

## 硬件能力边界（决定了大量"kernel 莫名崩溃"）

- **Triton grid 上限 65535**（NVIDIA 是 2^31−1）：任何按元素数算 grid 的 flag_gems kernel
  在大张量上溢出 —— `151936×4096` 的 embedding 做 `empty` 编出 607744 的 grid →
  `OutOfResources: grid size 607744 > 65535`。
- **同一个溢出在 decode 规模才触发，探针规模看不出来**：`_index_put_impl_` /
  `_unsafe_masked_index_put_accumulate` 的下划线前缀实现把 grid 推到 `batch*vocab`，
  serve 崩而 4×16 的探针假绿；按族前缀扫也匹配不到下划线名字，**只能逐条列举**
  （黑名单从 15 条涨到 223 条）。
- **`num_warps` 上限 4**（超了只 warn，属噪音）；**NRAM 每核上限 524288**：
  4096 宽的 tile 在 `num_stages=2` 必然超（nw=4 → 609024，nw=1 → 856400），
  所以 `BLOCK_SIZE1=4096` 永远赢不了，是纯崩溃触发器。
- **高级索引要求所有索引 dtype 一致**：`int64` 行 + `int32` 列 → `NOT_SUPPORTED`。
  逐条 setitem 写法在别的厂商能过，在这里必须先统一 dtype。
- **`bench()` 里挂掉的 autotune 不会自愈**：`RuntimeError: PassManager::run failed`
  （`AutoTileForTritonPass` 的 `tensor.expand_shape` 维度断言）在 `autotuner.py:160 _bench`
  抛出，但**不在** triton 的 `(OutOfResources, CompileTimeAssertionFailure, PTXASError)`
  捕获列表里 → 直接杀掉 EngineCore，而不是把该 config 标成 `inf`。
- **`flag_gems cumsum` 在 MLU 上算错**（不是慢），必须拉黑到 vendor/stock 路径；黑名单要写进
  配置 yaml 而不是插件 patch —— flag_gems 在 step 1 读黑名单，插件在 step 5 才加载。
- SDPA GQA 的 `repeat_interleave` 走 flag_gems 会**每个 decode step 重编一个 shape 特化 kernel**
  （随 KV 增长）→ 0.04 tok/s 且被 watchdog 杀掉；改成纯 view 展开
  （unsqueeze/expand/reshape + 一次 contiguous，与 repeat_interleave 逐字节等价）后 ~1.2 tok/s。
- 架构级缺口（属厂商事实，不是 app bug）：`torch_mlu` 把 `_C::get_mlu_view_from_cpu_tensor`
  注册成 CIA op 却没有 `torch.ops._C` 的 Python 句柄（abort `torch._inductor` 初始化）；
  `torch.accelerator.synchronize()` 没有 mlu 分支（`Backend doesn't support synchronizing all streams`）。

## 设备状态危险

- **孤儿进程占住 MLU 显存，看起来像镜像缺陷**：崩掉的引擎留下孤儿 `VLLM::EngineCore` 占
  MLU0 约 16.5 GiB，报 `62.68 GiB free < 67 GiB` 的假 OOM。通用签名是
  `Free memory ... < 0.6 utilization` —— **先查残留容器，不要先怀疑镜像**。
- **冷启动设备毒化（代价最高的一条）**：flag_gems 5.3.5 的 `libentry.py` `LibTuner.run()`
  在 cache-miss 分支会对**正在 decoding 的活张量**做在线计时 bench，污染 MLU 设备状态 →
  **只有冷首跑**（config DB 为空）输出乱码，热 DB 干净。唯一可靠判据 = 冷首跑 + 语义锚；
  热请求无法暴露。曾有一次「E2E 通过」就是这么假绿的（2026-08-26 发布的那次，无语义门）。
- 冷启动极慢，会在镜像还没问题之前撞框架 watchdog：300 s watchdog 会在 ~15 分钟时杀掉
  scheduler，需要 `--watchdog-timeout 900` + `SGLANG_WARMUP_TIMEOUT=1800`；ready 约 870 s，
  首请求冷调优可达 ~27 分钟（warm-cache 的 6–7 分钟是错的参照）。

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/cambricon.md`
- 4.7.2 的 workbook：`packaging/megatron/docs/megatron-0.18.2/workbook.md`
