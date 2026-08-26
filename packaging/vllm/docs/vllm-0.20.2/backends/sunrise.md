# vllm 0.20.2 — sunrise tangrt1.2.0

> 本文对应原报告第 2 部分 §2.9。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.9 sunrise-tangrt1.2.0（PTPU：✅ 官方 Triton E2E 通过；FlagTree 解码挂死缺陷 —— ✅ 已修复，见文末"后续"）

**有可用回退路径，并非硬阻塞。** 默认的 FlagTree 编译器下，serve 可起、预填充正常返回，
但进入**解码阶段即挂死**，卡算力占用钉在 100% 且永不退出。切到官方 Triton（`/opt/triton`）即可绕开。

**回退操作：** 在起 serve 的**同一个 shell** 里先执行 `compiler triton`（该命令只改当前 shell 的
`PYTHONPATH`，把 `/opt/triton` 前置），再启动 serve。`compiler flagtree` / `compiler` 切回或查看当前编译器。

官方 Triton 下 **serve + 推理端到端已验证通过，推理结果正确**。

**根因：FlagTree（triton 3.6.0）代码生成缺陷。** flag_gems `_sunrise` 后端的
`flash_varlen_fwd_kernel` 在**解码 + GQA** 特化（`seqlenq_ngroups_swapped`：
`max_seqlen_q==1`、q 头 32 > kv 头 8，导致 `cu_seqlens_q=None` 被 Triton 从签名中丢弃）
下被编译成不终止的 kernel。同一 kernel、同一入参改用官方 Triton 编译则正确完成——仅切换
编译器即完成归因。预填充特化（真实 `cu_seqlens_q`、batch stride 全 0）编译正常，故只有解码卡死。

已产出**不依赖 Docker / vLLM / 模型**的最小复现（`replay_min.py` + 277 KB 捕获入参），
FlagTree 下挂死、官方 Triton 下通过，待交厂商。

**影响：** 一旦挂死，该卡持续占用至设备/驱动复位或整机重启；`pt_smi -i <n> -r` 无法清除。

**后续（2026-08-19）：缺陷已修复。** 根因锁定在旧 vendor 标签
0.6.0+sunrise3.6（FlagTree **PR 978 之前**）的 sunrise 后端代码生成；
PR 978 重写 sunrise backend pass pipeline 并删除 `add_split_dot`（疑似
修复点）。已把 sunrise wheel 构建固化到 `packaging/flagtree/sunrise`
（PR #447→#450，22.04 + clang-14/lld-14 交付链，六道 CI gate 全过），
从 FlagTree main（含 PR 978）重建 wheel 后 A/B 实证：**解码 0.4 tok/s
（非终止）→ 2.4~2.5 tok/s（终止，输出连贯）**。节点复验在无
`LD_LIBRARY_PATH` workaround、无手动 tang 软链下通过（RUNPATH
`$ORIGIN`、md5 门禁、import/serve/推理全绿，详见
[0.24.0 §11.5](../../vllm-0.24.0/backends/sunrise.md)）。wheel 沿用原版标签上传
`flagos-pypi-sunrise`，可 drop-in 替换；本单元格 F 路径由"挂死"升级为 ✅。

**复测（2026-08-20）：0.20.2(F) 路径在 rebuilt wheel 下全绿。** 直接在
0.20.2 环境复测 FlagTree 路径（`compiler flagtree`，runtime 2.1.2 已烘焙
rebuilt wheel，`/opt/flagtree/triton/_C/libtriton.so` md5 924b1c0d 匹配
[0.24.0 §11.5](../../vllm-0.24.0/backends/sunrise.md) 门禁值），serve `/data/nmodels/Qwen3-8B` 达 `Application startup
complete`；推理连贯（knowledge "Paris..." / math "56"）、decode 正常终止
（2 请求均 `finish_reason=length`，无挂死）、崩溃标记 0。A/B 结论在
0.20.2 自身版本下成立，矩阵 `0.20.2(F)` 格 ❌→✅。

### 环境

| 组件 | 版本 |
|---|---|
| Python | 3.10.20 |
| torch | 2.11.0+cpu |
| torch_ptpu | 0.2.3+torch2.11 |
| FlagTree（triton） | 3.6.0 |
| flag_gems | 5.3.4 |
| vLLM | 0.20.2+flagos |
| 设备 / 驱动 | PTPU，sunrise / tangrt 1.2.0，tang 0.24.0 |

### 待办

1. **回退：切官方 Triton 运行** —— ✅ E2E 已验证：`compiler triton` 后 serve +
   推理端到端通过、结果正确；当前 sunrise 的可交付路径
1. **FlagTree flash-attn 解码 kernel 挂死复现交厂商** —— ✅ 已交付：最小复现
   （Docker-free，A/B 编译器归因）已交 FlagTree 团队
1. **FlagTree 侧修复落地** —— ✅ 2026-08-19：PR 978 已合入；重建 wheel 后 A/B
   实证解码 0.4→2.4 tok/s；F 路径升级 ✅（上文"后续"，详见
   [0.24.0 §11.5](../../vllm-0.24.0/backends/sunrise.md)）
