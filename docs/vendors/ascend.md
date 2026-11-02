# ascend（昇腾）

backend key：`ascend-cann8.5.0` / `ascend-cann9.0.0`（910B）以及各自的
`ascend-cann8.5.0-910c` / `ascend-cann9.0.0-910c`（910C）。全部 aarch64、python 3.11、
wheel tag `cp311-cp311-linux_aarch64`。

## 平台与设备

- 设备枚举命令 `npu-smi info`（runtime 镜像自带 `/usr/local/bin/npu-smi`；raw 档多挂的
  `/usr/local/sbin/npu-smi` 只是补 raw 场景的路径 —— 不要据此推断"镜像里没有 npu-smi"）。
- **index 是 die，不是卡**：一张 910C 卡 = 两个 die。`ASCEND_VISIBLE_DEVICES` 必须给
  显式 index 列表（`all` 会让容器创建直接失败）；容器内 `npu-smi info` **需要至少一个
  完整 die 对**（任何一对都行），单 die / 半板报 `-9005`，无 davinci 报 `-8005`，
  设备被占用报 `-8020`。
- **910C 是独立后端，不是 910B 的 tag 后缀**：只有 ops 包按芯片拆（token `910b` vs `A3`），
  但 CANN / flagtree / torch / flag_gems 在四条线之间都不同，**三条线（910B-8.5.0 /
  910B-9.0.0 / 910C 对）的结论不得互相套用**；跨变体差异多数源于 flagtree 版本。
- **910C 节点上容器 toolkit 已不再映射 davinci die**：非 privileged 启动
  `torch.npu.device_count()=0`（drvRetCode 87 / aclInit 507899），**`--privileged` 必需**；
  910B 上加它不回退。
- **pre-Ascend-950（含 910B4 全系）没有 flash-attn** → megatron 的动态引擎 RL 路径在本平台
  关闭，NPU 走自己的 paged attention。
- flags 原文见 `.github/build-config.yml` `run.vendors.ascend`（raw 档是 5 个设备节点 +
  3 个宿主挂载，缺 `davinci_manager`/`devmm_svm`/`hisi_hdc` 或 driver/dcmi 挂载起不来）。

## 容器内环境（本厂商最容易误判的一条）

- **CANN 全套 env 只发布给 bash 消费者**：base 把 `set_env.sh` 的结果抓进
  `/etc/profile.d/vendor.sh` 并设 `BASH_ENV=/etc/bash_env.sh`，`bash -c` 自动读到；
  Dockerfile 里手写的 `ENV LD_LIBRARY_PATH` 只是**短底**（不含 driver 目录）。
- **后果**：`sh`/dash、`docker run <img> <binary>`（无 shell）、systemd 只拿到短底，
  `libascend_dump`/`ml`/`trace` 找不到 `libascend_hal.so`；`docker run <img> sh probe.sh`
  **会假失败**，`bash probe.sh` 才是实况（曾据此把完好的 FlagCX `.deb` 误判为缺陷）。
  直接 `docker run <img> /flagos/bin/python -m vllm...` 绕过 bash → `torch_npu` 报
  `libascend_hal.so not found`。app launcher（`vllm-serve` / `sglang-serve` /
  `megatron-train`）就是为此存在：先 source `/etc/bash_env.sh` 再 exec。
  **这是已关闭的决定** —— 不要提议「修」`base/ascend-*` 让非 bash 消费者可用。
- 双编译器同属这一类（`/opt/flagtree`、`/opt/triton` 都不在 site-packages，激活的那个
  靠 `PYTHONPATH`）—— 平台无关的探针纪律见 `.claude/skills/node-ops/SKILL.md` §7。
- **`docker exec` 必须带 `bash -lc`**：裸 exec 走的是 Dockerfile 烘的**短版** env，
  `torch_npu` import 直接崩。也不要自己在 `LD_LIBRARY_PATH` 前面补 devlib —— 那里的
  `libascend_hal` 是**存根**，没有 `rtGetDevMsg`，补上反而设备初始化失败。
- `set_env.sh` 必须在 `bash -c` 里 source，不能放在 RUN 的 `/bin/sh`（dash）下：dash 下
  该脚本可能调 `exit`，在 `|| true` 兜住之前就静默杀掉整个 RUN。NNAL/ATB 的 `set_env.sh`
  必须在 CANN 的**之后** source：否则 `ATB_HOME_PATH` 与 ATB lib 路径缺失，`libatb.so`
  加载失败、`_npu_reshape_and_cache` / `_npu_rotary_embedding` 推理期崩；它还负责选
  `cxx_abi_1`（与 torch 的 ABI 对齐），选错是静默加载失败。

## 设备状态危险

- **Exited / 僵尸容器仍持有 NPU 句柄**：python 进程已 defunct 但 die 没释放，**下一个容器
  静默看到 `device_count=0`**，serve 在很后面报
  `AssertionError: DP adjusted local rank 0 is out of bounds. Device count: 0`（不点名真因）。
  `docker rm -f` 后同样的启动立刻拿到 `device_count=1`。
- **宿主侧探测不可靠**：`npu-smi info -t proc-mem` 会报 "No process in device" 而设备确实被占
  （外部 `open` 报 EBUSY）。**唯一权威判据是 `torch.npu.device_count()`**，配 `docker ps -a` 读。
  干净 910B4 单 die 空闲 HBM 基线约 3.4 GB，被占的 die 明显更高。
- **以下行不是失败信号**（在**通过的**日志里也刷）：`path string is NULL`、
  `DrvMngGetConsoleLogLevel failed (ret=4)`、`dcmi -8020`。"out of memory"/"device busy"
  先查残留容器。
- **冷启动 JIT 极慢，按 metrics 判完成而非客户端超时**：首请求 7–15 分钟（T 路径实测 872 s），
  64 token ≈ 11–15 分钟；判据 = `vllm:generation_tokens_total` 在涨 +
  `num_requests_running` 归零。`docker exec` 里的 curl 写的是**容器**的 `/tmp`。

## 供应商工具链

- 两个编译器树**都自报 `triton.__version__ == 3.2.0`**，必须按编译器分别设
  `TRITON_CACHE_DIR`，否则 cache 互相污染。
- `flag_gems` 需要可 import 的 triton；import 不到时 `supports_paged_attention()` 退化成
  flash-attn 版本门并 assert —— 「编译器不在 PYTHONPATH 上」会表现为一个无关的 attention 断言。
- **`flag_gems.enable()` 污染 `torch_npu`**（serve 起不来）→ 当前定案 **`USE_FLAGGEMS=0`**。
  逐算子黑名单试过（用户否决整片屏蔽），清完崩溃后吞吐仍是病理的 ~0.05 tok/s（OFF 为
  10.2 tok/s），故回到整片关闭这一背书基线；黑名单保留作文档，OFF 下 inert。
  调黑名单**不要**用 `*_FLAGOS_*` 环境变量：它**整体替换** yaml 列表。
- 平台签名（认出来就别当 app bug）：标量/零 grid launch → `coreDim is invalid (value 0)`；
  喂给 `_npu_reshape_and_cache` 的 k/v 是 2D flat → `ATB op setup failed` / `507035`
  （**硬要求 3D head 布局**）。
- ⚠️ **绿格可能是偶然的**：vllm 0.20.2/T 黑名单漏了 `repeat_interleave_*`，vendor rope
  首次 decode 编译失败后**静默回退** `default.flagos` rope，掩盖了 0.24.0 黑名单才暴露的
  上游缺陷。**跨栈搬运 ✅ 前先 diff 两侧黑名单。**

## 平台级 kernel / op 地雷

- **`torch_npu.atb._npu_paged_attention_v2` 只在 (block_size, head_size) 的稀疏格子上算对，
  其余静默算错**（无报错，输出保持 init 值 → 零注意力 → 垃圾 logits；hs>256 则 aicore 异常
  杀进程）。910B4 实测：blk=128 全范围可用；blk=256 安全区 = hs≤64 或 hs==256；
  blk=512 仅 hs≤32 或 hs==256。**生产风险 = Llama 类 hs=128 × megatron 默认 blk=256
  → patch 必须加 guard**（RL 配方 blk=256/hs=16 在安全区）。
  该算子**支持 bf16**（hs=16/blk=256/bf16 探针 diff=0.0000），走它不需要 dtype 转换。
- **prefill 走 `npu_fusion_attention(..., "TND", ...)`**：`triu(ones(bool),1)` 即精确 varlen
  causal mask。**KV 必须先按 block_table 索引再 reshape** —— 反过来是错位垃圾。

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/ascend.md`
- 节点 ↔ hostname ↔ runner 标签：`scripts/verify-nodes.example.yaml` +
  `.github/build-config.yml` `runners.overrides`
