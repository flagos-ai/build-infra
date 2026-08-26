# vllm 0.20.2 — enflame tops1.10.6/tops1.9.10

> 本文对应原报告第 2 部分 §2.6。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.6 enflame（GCU300：✅ E2E 通过，vLLM 原生 FLASH_ATTN，跨栈收敛）

**方案:** vLLM 原生 FLASH_ATTN + 五处修复（plugin A/B/C/E [PR #357](https://github.com/flagos-ai/vllm-plugin-FL/pull/357) + flag_gems D [PR #5345](https://github.com/flagos-ai/FlagGems/pull/5345)）。

**跨栈收敛（关键结论）:** 同一份代码在 **tops1.10.6**（torch_gcu 2.11，首次推导 2026-08-09）
与 **tops1.9.10**（torch_gcu 2.10.0，复验 2026-08-09）上**零改动**通过 E2E——不再是每栈一个
方案。此前 1.9.10 上的 `AttentionFLBackend` 记录（旧 §2.6.1）已删除：其诊断（int64 双层结构、
采样根因）已被本节 + §2.6.2 覆盖，且被更贴近上游的原生 FLASH_ATTN 路径取代。

> **约束提醒（贯穿两栈）：** GCU300 的 triton 后端（`make_gcuir` 的 PassManager）彻底拒绝
> 64 位数据类型——不是前端 / FlagTree 问题，换 triton 前端无用，拒绝发生在 GCU300 codegen
> 后端。五处修复中 A/D/E 都是绕这堵 64 位墙。

### 2.6.1 tops1.10.6 干净重推导（✅ E2E 通过，2026-08-09）—— 首次推导

**日期:** 2026-08-09　**平台:** Enflame GCU300

**镜像:** `flagos-runtime-enflame-tops1.10.6:2.1.2`

**stack:** torch_gcu 2.11 / tops1.10.6 / **flag_gems master（editable）** / plugin main（editable）

从零容器起、不预置任何补丁，逐个由硬件暴露的失败驱动修复。采用 **vLLM 原生 FLASH_ATTN**
（干净 plugin main 已改用该路径——更贴近上游、用厂商快内核）：原生后端需要把厂商 flash_attn
的计算算子与 flag_gems 的 KV 写内核接进 vLLM。此方案已提 PR（#357 / #5345），并在 1.9.10 栈上
复验通过（见 §2.6.2），确认跨栈收敛。

#### 五处修复（均在 git 可追踪的 editable flag_gems / plugin 内，vLLM site-packages 保持原样）

- **A** —— 模型加载期 flag_gems int64 工厂/索引算子（`zeros`/`add`/`sub`…）触 GCU300
  64 位墙：plugin 配置 `enflame.yaml` 黑名单回退 torch_gcu
- **B** —— `FlashAttention version not detected`（空 wheel 无 `_vllm_fa2_C`）：plugin
  `__init__.py` 早期把厂商 `flash_attn.vllm_flash_attn` 别名到 `vllm.vllm_flash_attn`
- **C** —— `reshape_and_cache_flash` NameError（empty build 剥离 `vllm._C`）：plugin
  `gcu/impl/flash_attn_backend.py` 把厂商 FA 计算 + flag_gems KV 内核绑上 `fa_utils`
- **D** —— flag_gems `reshape_and_cache_flash` 内核收 int64 `slot_mapping`：flag_gems
  `fused/reshape_and_cache_flash.py` 降位 int32
- **E** —— vLLM 原生 `_compute_slot_mapping_kernel` 内建 int64：plugin
  `gcu/impl/slot_mapping.py` 纯 torch on-device int32 重写

#### 设计取舍

**B/C 为何是插件层、且 vLLM 保持原样。** 两者都可直接改 vLLM `fa_utils.py`，但那是 empty
build 的 wheel，站点包手改不可复现。改为在 `apply_gcu_patches()`（GCU 后端加载时运行）里
绑定：C 把厂商 `flash_attn_varlen_func`/`get_scheduler_metadata` 与 flag_gems
`reshape_and_cache_flash` 绑上 `fa_utils` 并强制 `is_flash_attn_varlen_func_available()`→True。
补丁对导入顺序稳健——若 `flash_attn.py` 已先导入（其加载期条件导入已跳过这些名字），则同时
把这些名字注入该模块命名空间。全程以 `torch_gcu` 存在为门（enflame 专属），厂商无 flash_attn
包时静默回退、不影响其他后端。

**D/E 都要、且不冗余。** E 重写 `slot_mapping` 的**生成**（vLLM 原生内核），D 降位
`slot_mapping` 的**消费**处（flag_gems KV 写内核）。vLLM 的 `slot_mapping.gpu` 缓冲区 dtype
为 int64，E 产出的仍是 int64，故 D 在消费端的降位仍然必要。A 覆盖的是加载期的 L1 工厂/索引
算子，早于任何注意力路径，独立于 D/E。

**E 采用 on-device int32 而非 CPU-int64。** 缓存槽位空间（`num_blocks * block_size`，现实
配置 ~1e8）远在 int32 上限（~2.1e9）内，全程 int32 可绕开 64 位墙又无 host round-trip。
token→request 映射用 `torch.searchsorted(qsl[1:], tok, right=True)`，而非
`repeat_interleave`——后者在 GCU300 flag_gems 走 index_select 内核，grid.y 上限 255，超
~4080 token 即崩。落库前用 CPU-int64 参考对拍 5 组用例（含 4096 token、max_slot ~2.08M），
逐元素 bit-identical。

#### Stack 验证（enflame-tops1.10.6，✅ E2E 通过 2026-08-09）

```
vllm:         0.20.2+flagos           ✅  empty，enflame 本地 build（cp312），site-packages 原样
vllm_fl:      main f4ebc258 (editable) ✅  A 配置改名 + B FA 别名 + C FA/KV 绑定 + E slot_mapping 重写（PR #357）
flag_gems:    master 469bb00d (editable)✅  D reshape_and_cache_flash slot_mapping int32（PR #5345）
torch_gcu:    2.11                    ✅  透明 Long→Int（torch 层无 64 位问题）
GCU device:   ✅ 可见
推理:         Qwen3-4B → "Paris"      ✅  连贯英文，20→64 token，finish_reason=length，HTTP 200 9.2s
```

**环境：** vendor triton（`compiler triton`）+ `VLLM_PLUGINS=fl`，Qwen3-4B TP=1 max-len 4096
enforce-eager，`/root/run_serve.sh` 现场保留。两处插件 patch 日志（主进程 + worker）均出现：
`enabled native FLASH_ATTN backend` 与 `patched BlockTable.compute_slot_mapping (on-device int32)`。
完整变更即本节所述（§2.6.1）。

### 2.6.2 tops1.9.10 跨栈复验（✅ E2E 通过，2026-08-09）—— 零改动 + 采样缺口修复

**日期:** 2026-08-09　**平台:** Enflame GCU300

**镜像:** `flagos-runtime-enflame-tops1.9.10:2.1.2`（runtime v2：仅预置 flag_gems，**无 vllm、无 plugin**）

**stack:** torch_gcu **2.10.0** / tops1.9.10 / flag_gems master（editable）/ plugin #357（editable）

在 1.9.10 栈全新 v2 容器上复验 §2.6.1 方案，判定是否可退役 1.9.10 上的 AttentionFLBackend。
纪律：vllm 从厂商 index 单步装（`vllm==0.20.2+flagos`，非磁盘捞取），flag_gems / plugin 走
上游 PR 树 editable，无手改。**环境变量策略：** 仅显式 `compiler triton`（flagtree 不信任，
故明确选 vendor triton），不设任何其他环境变量——`VLLM_PLUGINS=fl` 经确认冗余（plugin 靠
entry point 自动发现）。完整记录即本节所述（§2.6.2）。

**结论 1 —— 贪心零改动通过（跨栈收敛坐实）：**

```
vllm:         0.20.2+flagos（vendor index 单步装）   ✅  site-packages 原样
vllm_fl:      #357 分支 6e35613 (editable)            ✅  A/B/C/E 全部生效
flag_gems:    master 3f5fb04 (editable, Fix D 已合并)  ✅  D
torch_gcu:    2.10.0                                  ✅  vs 1.10.6 的 2.11，无需代码差异
compiler:     vendor triton（compiler triton）        ✅  显式，flagtree 不信任
推理:         Qwen3-4B, greedy → 连贯英文             ✅  "…Paris is the capital"，HTTP 200，27.8s
```

五处修复跨 torch_gcu 2.11 → 2.10.0 **全部零改动移植**，唯一磕绊是环境性的（残留兄弟容器占住
GCU 0 显存，`docker rm -f` 解决），非代码缺口。

**结论 2 —— 采样（temp>0）缺口：贪心 E2E 看不见的真实洞，已修（配置层）：**

贪心走 `argmax`，不触发 top-k/top-p sort 路径。显式测采样（`temp=0.8, top_p=0.9`）逐个由
硬件失败驱动、增量补 GCU300 dispatch 黑名单（每个 op 都由一次现场失败换来，非照搬旧笔记）：

- `sort` / `sort_stable` —— **int64 墙：** 崩溃 `logits.sort()` → gcu300 radix_sort int64
  → PassManager 拒绝
- `rsub_scalar` / `rsub_tensor` —— **int64 墙：** 崩溃 top-k `logits_sort.size(1) - k`
  → rsub int64 → 同墙
- `argmax` —— **correctness：** 退化输出（空/纯空白，不崩溃）：flag_gems gcu300 argmax
  大词表下返回越界 token id；torch_gcu argmax 正确

修复为纯配置（路由到 torch_gcu），enflame 专属。补齐后 `temp=0.8/top_p=0.9` 在 Qwen3-4B 上
输出连贯（两个 prompt 确认）。未加密（`q.exponential_()`）经探针确认在 GCU300 上正确，无需
黑名单。**已推 #357（commit 851bbda）。**

**结论 3 —— flag_gems gcu300 argmax 是真实内核 bug（根因已定，非 `and`/`&`）：**

追到根因：`argmax.py:103` 的 `and`→`&` 反模式**不是**修复——改后清全部缓存、debug log 确认
补丁内核确实执行，仍返回越界 id。探针刻画：词表门槛（V≤32768 对、V=151936 错，需多 tile
`BLOCK_N` 循环）+ 偶数行奇偶性（B=8 行 0/2/4/6 错、1/3/5/7 对），错值是最后一个 tile 的被
mask lane。**根因：GCU300 triton_gcu 跨 tile 归约累加的 codegen 误编译（偶数 lane 奇偶性）。**
`and`-on-tensor 反模式确实广泛存在（~50 处 / ~20 个 gcu300 算子）但修它不改 argmax 行为，两
件事分开。已生成面向厂商的中文根因报告（`flaggems-gcu300-argmax-bug.md`，**待移交** docs 目录）。
已验证的生产修复仍是黑名单（argmax → torch_gcu，已在 #357）。

#### 待办 / 落库

- **本节为 enflame GCU300 唯一主路径，跨栈收敛已坐实**（1.10.6 + 1.9.10 同一份代码零改动通过）。
  旧 §2.6.1（1.9.10 AttentionFLBackend 历史记录）已删除，诊断内容并入 §2.6.2。
- **已落库**：五处修复 + 采样黑名单已提 PR（均直推 flagos-ai）：
  - **plugin（A/B/C/E + 采样黑名单）→ [PR #357](https://github.com/flagos-ai/vllm-plugin-FL/pull/357)**：分支 `enflame-gcu300-native-flash-attn` → `main`。走 vLLM 原生 FLASH_ATTN。**注：** slot_mapping / fa_utils 绑定耦合 vLLM v1 worker/attention 布局，须对齐 vLLM 0.24.0 迁移后重新推导。
  - **flag_gems（D）→ [PR #5345](https://github.com/flagos-ai/FlagGems/pull/5345)**：分支 `enflame-gcu300-reshape-cache-int32` → `master`。vendor+dtype gated 的 slot_mapping int32 降位，与 vLLM 版本解耦。
- **flag_gems gcu300 argmax codegen bug** → 中文厂商报告（`flaggems-gcu300-argmax-bug.md`，**待移交** docs 目录），待发厂商 triton_gcu 团队；修复后可从 #357 黑名单移除 `argmax`。
- 仅测单轮 64 token 生成；多轮 / 长上下文未验。
- 加密采样（`exponential_(generator=)`）未测。
- E 的 CP>1 交织分支已实现但未测（本配置 cp_world=1）。
- 运维备忘：teardown 需一并 `pkill -9 -f "EngineCore"`——spawn worker 不匹配
  `[v]llm serve`，残留会占住 GCU 显存致下次启动 OOM；已完结的验证容器也需 `docker rm -f`。
