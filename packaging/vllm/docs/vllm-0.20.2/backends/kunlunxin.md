# vllm 0.20.2 — kunlunxin xre5.37.1

> 本文对应原报告第 2 部分 §2.10。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.10 kunlunxin-xre5.37.1（P800 XPU：✅ 双编译器 E2E 通过；解码乱码 / 假死 —— ✅ 双闭环）

**结论（2026-08-22~23）：** 0.20.2 双编译器路径均 E2E 通过 —— FlagTree（默认）
7/7（7.3~9.8 tok/s）、Triton 3.6.0 3/3（5.7~7.3 tok/s），serve + 推理连贯。
此前两个阻塞（解码乱码、解码假死）均已 A/B 定位根因并闭环；旧阻塞（三处
attention 内核编译失败）由厂商插件层 **PR #268**（xtorch_ops 原生 attention
backend，不碰 Triton 编译）+ triton 3.6.0 升级（#469）解除。解码乱码根因详见
[`kunlunxin-decode-repetition-scale-bug.md`](../../kunlunxin-decode-repetition-scale-bug.md)。

### 阻塞点与闭环

**P2 解码乱码 —— 插件 patch 传错 attention scale（已闭环，PR #400）。**
`patch_decode_attention`（`patch.py:401`）把 decode 借道
`xtorch_ops.prefill_attention` 时传 `alpha=scale`（≈0.0884），而
`prefill_attention` 期望 adjusted scale（`scale×√head_size` = 1.0，原生 prefill
路径即如此）。α 小 √128 ≈ 11.3 倍 → QKᵀ 打分整体收缩 → softmax 趋平 → 输出
重复退化（greedy 下高频 token 主导）。一行修复 `alpha = scale × √head_size`
后，probe 对照 native 路径 max error 0.0014、serve 输出连贯。修复已上提
vllm-plugin-FL **PR #400**（base **release-0.2** = 0.20.2 发布线；upstream main
已删除 vendor/kunlunxin 目录，0.24.0 线无挂点），body 含双编译器验证记录。

**P1 解码假死 —— 触发源 = `XPU_EVENT_KL3_ENABLE=1`（已闭环，配方去掉该行）。**
KL3 事件/同步路径（`torch_xmlir/xre/so/libxpucuda.so.515.58.kunlun`，与
get_cluster_clock 同 .so）在异步提交路径引发设备异常。A/B 单变量法：基线
（KL3=ON）6 次启动 2 次跑通、9 次 XPUW err-task（get_cluster_clock + Xid
KL_XID_KERNEL_EXCEPTION，内核态 dmesg，签名跨事件一致）；**unset KL3 后
flagtree 7/7 + triton 3/6.0 3/3 全跑通 + dmesg 零新事件**。CUDA_LAUNCH_BLOCKING=1
亦可消除（错误提示自带）但吞吐减半。假死链路：解码步设备异常 → 看门狗 20min 后
报 get_cluster_clock → error 702 在 patch.py:72 compute_slot_mapping 浮出 →
退出期 `_prepare_to_exit→synchronize` 永久挂起。与具体算子无关（无需换
flag_gems 实现）。

**app 镜像 serve 慢 —— 根因 = env 缺失（export 缺陷），不是 block-size（2026-08-23
闭环，PR #478）。** 原 configs.yaml kunlunxin 仅 `env.base`、无 `env.app.vllm` → app
镜像零 serve env；补四变量（`VLLM_FL_PLATFORM=kunlunxin`、`VLLM_FL_PREFER=flagos`、
`USE_FLAGGEMS=1`、`VLLM_FL_FLAGOS_WHITELIST=silu_and_mul,rms_norm,rotary_embedding`，
#476）后，plain `docker run <app镜像>` 仍慢到 ~0.1 tok/s。2×2 控制实验定案：同一镜像、
同一 CLI、同一 block-size=16，仅差这四变量 → 6.4 vs 0.1 tok/s，env 是差别因子，bs 不是。
链路断点在 Containerfile：`/etc/profile.d/app_env.sh` 以裸 `KEY=value` 写入，vllm-serve
source 后 `exec` 新进程 → 非 export 的赋值随 sourcing shell 消失，到不了 exec 的 server。
修复（PR #478）：runtime/Containerfile + app/vllm/Containerfile + app/megatron 两个
Containerfile 写 profile.d 时统一 `sed 's/^/export /'` 前缀；同时修正 app/vllm 默认 CMD
模型路径 `/data/models/Qwen/Qwen3-4B` → `/data/models/Qwen3-4B`（旧路径在参考节点不存在，
plain `docker run` 直接 model-not-found）。`configs.yaml` 数据与 `generate_matrix.py`
序列化（保持 `KEY=value`）不动 —— export 属于 Containerfile 层，直接 CLI 构建也覆盖。
重建后 plain `docker run <image>`（无参数，走默认 CMD）验证：`/data/models/Qwen3-4B`
正常加载，exec 后的 server 进程 `/proc/1/environ` 含全部四变量（export 生效的直接证据），
推理 4.3~9.4 tok/s 且输出连贯（对照修复前 0.1 tok/s 乱码）。app 镜像指纹：
`vllm0.20.2-kunlunxin-xre5.37.1:2.1.2-0.2.1_g8236c0a.d20260821`（ID 229fda5f9ee9…）。
**KL3 刻意不固化**（修复 = 缺省，容器默认 env 本就干净）。

### 环境

| 组件 | 版本 |
|---|---|
| 镜像 | flagos-runtime-kunlunxin-xre5.37.1:2.1.2-vllm-kx-20260822（ID 56c73455d509） |
| Python | 3.10 |
| torch | 2.9.0+cu129 |
| FlagTree（triton） | 0.6.1+xpu3.6 |
| Triton | 3.6.0+gitcd2d6c1b |
| flag_gems | 5.3.4 |
| xtorch_ops | 0.1.2935+50a5d6a4 |
| vLLM | 0.20.2+flagos |
| 设备 / 驱动 | P800 XPU / 5.37.1 |

### 待办

| 事项 | 状态 | 备注 |
|------|--------|-------|
| alpha 修复上提 vllm-plugin-FL | ✅ PR #400 | base release-0.2（0.20.2 发布线）；body 已补双编译器验证记录 |
| app 镜像 serve E2E（plain docker run） | ✅ PR #478 | 2026-08-23 重建后验证：默认 CMD 模型路径 + export env + 4.3~9.4 tok/s |
| Qwen3.6-27B 回归 | ⬜ | patch 初衷是规避 layer 43+ decode NaN，修复 scale 后须重验 |
| 源文档配方更正（去掉 KL3 行） | ⬜ 待拍板 | 复刻源文档 3 处含 `XPU_EVENT_KL3_ENABLE=1`，已定负面教材不改 |
| 0.24.0 验证 | ⬜ | upstream main 已删 vendor/kunlunxin 目录，0.24.0 线无插件挂点 |
