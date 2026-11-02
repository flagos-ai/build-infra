# enflame（燧原）

backend key：`enflame-tops1.9.10` / `enflame-tops1.10.6`。芯片 Zixiao C200（S60），
SDK 叫 TOPS/tops。python 3.12，torch 是 `torch-gcu`（**PrivateUse1**）。

## 平台与设备

- 设备枚举命令 `efsmi`；一节点 8 卡。
- **两个可见性变量必须同时设**：`ENFLAME_VISIBLE_DEVICES` 与 `TENCENT_VISIBLE_DEVICES`
  —— 腾讯云与自建环境各读其中一个，只设一个会让另一个静默为空。
- **toolkit 档带 host 网络而不用 `--runtime`**（该厂商没有容器 runtime）；raw 档是
  privileged + 整设备树挂载。**给 toolkit 档再补一次 host 网络**会让 `docker run`
  直接拒绝启动（"network host is specified multiple times"）—— verify 脚本为此特判
  enflame，仅在没看见 host 网络时才补。
- flags 原文见 `.github/build-config.yml` `run.vendors.enflame`。

## 供应商工具链

- **平台名与设备名是两个不同的字符串**：`vendor_name=enflame`、`device_type=gcu`。
  dispatch 配置文件按 device 命名（`gcu.yaml`），所以 `get_config_path` 少了
  device-name 别名回退时，`op_backends` **和** `flagos_blacklist` 会**双双静默取空**。
  同理**注册期**读 `current_platform` 做门的补丁会静默失效（那时还是
  `UnspecifiedPlatform`）——能用的门读 `DeviceInfo` 且接受两种拼写。
- **64 位墙在 GCU300 的 codegen 后端，不在前端**：`make_gcuir` 的 PassManager 彻底
  拒绝 int64。换 triton 前端或用 FlagTree 都不改变结论，多组修复存在的唯一目的就是
  绕它。
- **`ENABLE_I64_CHECK=0` 在 serve 路径上是 no-op**：`parse_options` 只在调用方显式传
  `enable_i64=False` 的 `elif` 分支里读该环境变量，而 inductor 从不传这个键 →
  `24*ks0` 这类地址运算照样报 `64-bit data type not supported on GCU300`。**无绕法**，
  这是 graph 模式不能做出货门禁的原因。
- **硬性 grid 上限：grid.y ≤ 255、grid.x ≤ 65535**。`repeat_interleave` 会走 flag_gems
  的 `index_select` 内核、超 ~4080 token 即崩；q_norm 内核的 `batch × 32` grid 在 2048
  token 上溢出（2048×32 = 65536）——`max_num_batched_tokens` 被钳到 2047 就是这个原因。
- torch_gcu 别名 CUDA 但门面不全：**没有 `Tensor.exponential_(generator=)`**
  （带 seed 的采样路径必须换成无 seed 版，代价是失去 per-request 可复现性，
  `_dummy_sampler_run` 也踩同一个洞）；**设备属性类缺 `is_integrated`**（sglang
  scheduler 每次 kernel load 都读它，缺字段抛的是 `AttributeError` 而不是
  `RuntimeError`，**直接杀掉 scheduler**）。
- **`import` 期就抛异常**：`third_party/enflame/backend/toolkit.py` 在
  `/opt/triton_gcu` 不存在时 import 即 `raise` —— 全 flagtree 树里唯一这样的后端
  （其余都在函数内抛）。该目录只由厂商那个 ~3.3 GB 的 `triton-gcu` deb 创建，
  **裸构建机连 wheel 都 import 不了**；搭 flagtree-enflame 的环境必须先把 deb 备好。
- fa3 factory 断言 `SM>=80`，stock wrapper 又要求 "flash_attn only on sm90+"，
  两道门都拒绝 GCU —— 厂商 FA 只能直调。
- 厂商 `silu_and_mul` 与 reference 逐字节相同，其 dispatch 档位已删除（只会遮蔽回退）。

## 平台级 kernel / op 地雷

- **flag_gems `argmax` 在 gcu300 上静默返回越界 token id**（大词表，不崩溃）。
  贪心路径走 argmax 但**不触发** top-k/top-p 的 `sort`/`rsub`，所以**贪心通过完全不能
  背书画采样栈** —— 必须显式跑 `temp>0`。`sort`/`sort_stable`/`rsub_*` 则撞 64 位墙而崩。
  根因是 `triton_gcu` 跨 tile 归约的 codegen 误编译（偶数 lane 奇偶性）；记录在案的
  `argmax.py:103` `and`→`&` 反模式**不是**修复。
- **ECCL 拒绝 fp64 `all_reduce`（int64 同样不支持）**，其他厂商的 collectives 接受
  double。启动路径上任何用 `dtype=torch.double` 同步 timestamp 的代码都在 step 1
  之前死在 `DistBackendError … ecclInvalidArgument`；fp32 是唯一验证过的替代。
- **`all_gather_object` 在 WORLD_SIZE==1 时返回垃圾 size**（实测
  `-4888733163028742123`），`resize_` 于是试图分配 ~1 EB 立即 OOM；
  `torch.gcu.synchronize()` 无用，普通 `all_gather` 各 dtype 都正确。
- **不要按栈重推结论**：torch_gcu 2.10.0 与 2.11 上同一份代码零改动通过，在 1.10.6 上
  推出来的修法不要为 1.9.10 再推一遍（反之亦然）。

## 设备状态危险

- **spawn worker 的进程名是 `EngineCore`，不匹配 `[v]llm serve`**：残留 worker 占住
  GCU 显存，下一次启动报 OOM，**看起来像镜像缺陷**。teardown 要
  `pkill -9 -f "EngineCore"` **加上** `docker rm -f`。同一签名也出现过在"残留兄弟容器
  占住 GCU 0"上，`docker rm -f` 即解。
- **冷启动极慢**：triton prefill kernel 每次编译约 20 s，serve ready 分钟级（app 镜像
  实测 ~315–555 s），verify 要放宽客户端超时，否则把冷启动判成失败。

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/enflame.md`
- all_gather_object / ECCL 的现场报告：`packaging/megatron/docs/megatron-0.17.1/handoffs/`
- 编译器构建事实：`packaging/flagtree/README.md`（Enflame builder 段）
