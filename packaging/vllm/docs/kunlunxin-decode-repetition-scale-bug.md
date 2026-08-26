# 昆仑芯 P800 XPU — vLLM decode 重复退化根因（厂商 hand-off）

**日期：** 2026-08-21　**报告人：** FlagOS 集成验证
**硬件：** 昆仑芯 P800 OAM　**XRE：** 5.37.1（driver 5.37.1.0）　**架构：** `xpu_arch=3` / xpu3
**场景：** vLLM 0.20.2（empty build）+ vllm-plugin-FL（含 kunlunxin vendor 插件层 #268）+ flag_gems 5.3.4（`_kunlunxin` 后端），serve Qwen3-4B，TP=1，block_size=128，enforce-eager，temperature=0.0
**torch：** 2.9.0+cu129（stock）+ torch_xmlir　**decoder：** 厂商 `xtorch_ops`（v0.1.2935+50a5d6a4，本地 wheel 手工注入，见 §4）

---

## TL;DR

Qwen3-4B 在**移除 `USE_RESHAPE_AND_CACHE_FLASH=1`** 后不再乱码，但出现**确定性重复退化**（输出 "，实现的一个一个一个一个一个问题的的的"，temperature=0.0 greedy 可复现）。根因定位在厂商插件层 `patch_decode_attention`：它用 `xtorch_ops.prefill_attention(..., is_prefix_cache=True)` 替代 `decode_paged_attention` 时，**传错了 attention scale** —— 传了原生 decode 的 `alpha = scale`（≈0.0884），而 `prefill_attention` 期望 adjusted scale（`scale × √head_size` = 1.0，原生 prefill 路径 `context_forward` 即如此）。α 小 11.3 倍 → QKᵀ 打分整体收缩 → softmax 趋平 → 注意力摊平到整个上下文 → greedy 解码被高频 token（"的"、"一个"、"一"）主导 → 重复环。

**一行修复已实证**：`alpha = scale * sqrt(head_size)` 后输出恢复正常（12-token 与 30-token 均流畅，无重复退化）。**native `decode_paged_attention` 对照同样正常** —— 即厂商两条 decode 路径都能出正确结果，唯独 patch 借道 `prefill_attention` 时 scale 传错。

- **归属：** 厂商插件层（`vllm_fl/dispatch/backends/vendor/kunlunxin/patch.py`）自身缺陷，与 vLLM 上游、FlagTree、FlagGems 均无关。
- **与乱码的关系：** 乱码是**另一个独立故障**（`USE_RESHAPE_AND_CACHE_FLASH=1` 时 block_table 翻倍读错 KV offset，写入侧），与本次读取侧 scale 错误无关，两条链不互相污染。

---

## 1. 症状与复现

Qwen3-4B，请求 `temperature=0.0`（greedy），`max_tokens=12`：

- **原 patched** —— `prefill_attention(prefix_cache)`，alpha 传 **0.0884（=
  scale，错）**：输出 "，实现的一个一个一个一个一个问题的的的"
- **修正 patched** —— 同左，仅 alpha 改为 1.0（= adjusted_scale）：输出
  "，用于在Windows系统中，将一个文件夹复制"
- **native decode** —— `decode_paged_attention`（该 kernel 期望 raw scale）：
  输出 "，用于在Windows系统中部署一个简单的Python环境，"

30-token 长请求在修正后同样流畅（"…然后运行一个简单的容器，比如一个Ngin"）。三种模式下 KV 写入读回（见 §2）均 `rb_diffmax=[0.0]` —— 写入/记账始终正确，唯一变量就是 decode 读取侧的 scale。

## 2. 排除项（已插桩实证）

- **KV 写入槽位/内容错误** —— **证伪**：KVW 读回：写入 key 与缓存逐位一致
  （`rb_diffmax=[0.0]` 每层每步），slots 136→137→138…、seq 9→10→11… 正确递增
- **长度/计数链错误** —— **证伪**：`seq_lens` 9→37 递增（8 prefill + 29 decode），
  `[DECD]` 的 kvpsl 同步递增，`block_tables` 首 block=1 正确
- **slot_mapping 槽位计算错误** —— **证伪**：`compute_slot_mapping_xpu` 审读：
  `slot = block_numbers × block_size + positions % block_size`，与实测一致
- **decode position ids（rotary）错乱** —— **证伪**：native decode 输出正常
  （同一位置序列），且修正 scale 后 patched 也正常 —— 位置链本身无问题
- **采样随机性** —— **排除**：temperature=0.0 确定性输出，可稳定复现

## 3. 根因机制

`xtorch_ops` 两个 kernel 的 scale 语义不同：

- `decode_paged_attention` 期望 **raw scale**（`1/√head_size`，native 路径传 `self.scale`，正确）。
- `prefill_attention` 期望 **adjusted scale**（`scale × √head_size` = 1.0，`context_forward` 传 `self.adjusted_scale`，正确）。

`patch_decode_attention` 把 decode 借道 `prefill_attention` 时沿用了 decode 的 raw scale，α 小 √128 ≈ 11.3 倍 → logits 全部收敛到 0 附近 → softmax 近均匀 → 每个 decode 位置看到的都是"整段上下文的加权均值"，失去位置区分力 → greedy argmax 被高频 token 主导，形成**确定性重复环**（而非随机乱码）。这也解释了为何症状是"重复"而非"乱码"。

## 4. 可复现性缺口（须厂商配合）

本验证环境依赖**厂商手工注入的 `xtorch_ops` wheel**（v0.1.2935+50a5d6a4，`cp310-cp310-linux_x86_64`）：

- PEP 610 `direct_url.json` 显示安装来源为 `file:///opt/docker/output/xtorch_ops-0.1.2935+50a5d6a4-cp310-cp310-linux_x86_64.whl`（本地文件，装完即清理，`/opt/docker/output/` 现已不存在）。
- **vendor index 上无此包**：`pip download --index-url .../flagos-pypi-kunlunxin/simple xtorch_ops` → `from versions: none`。
- **build-infra 管线未固化**：configs.yaml kunlunxin `deps:`（14 个包）无、`runtime/Containerfile` 无、base Containerfile 无、已装包无 `Requires-Dist: xtorch_ops`。
- **标准 runtime 镜像不含它**：直接检查 `flagos-runtime-kunlunxin-xre5.37.1:2.1.2` 的 venv，`grep xtorch` 为空。

即：当前验证与上述结论建立在一次性手工注入环境上，**无法在干净镜像上复现**。需要厂商将 xtorch_ops 上传至 `flagos-pypi-kunlunxin` 索引（含版本 + 依赖元数据），build-infra 才能将其加入 `deps:` 固化进 runtime 镜像。

## 5. 处置

- **修复（一行）**：`patch_decode_attention` 中 `alpha = scale * (head_size ** 0.5)`（即复用 `self.adjusted_scale`）。
- **回归**：该 patch 初衷是规避 Qwen3.6-27B layer 43+ decode NaN，修复 scale 后须在 27B 上重验，确认 NaN 规避仍成立且无退化。
- **上架**：xtorch_ops 上传 vendor index（见 §4），消除手工注入依赖。
- **后续**：建议厂商核对 `prefill_attention` 与 `decode_paged_attention` 的 scale 约定是否还有其它调用点踩同一坑（如 `context_forward` 之外的分支）。

---

## 更新（2026-08-23）：可复现性缺口已关闭，修复已上提

- **xtorch_ops 已入管线**：configs.yaml kunlunxin `deps:` 自 #469（2026-08-21）起
  含 `xtorch_ops==0.1.2935+50a5d6a4`（deps 共 17 包），重建的 runtime 镜像直接携带，
  不再依赖 §4 所述手工注入。vendor index 上架状态以厂商为准（容器层/节点/索引
  wheel 逐字节一致已核）。
- **修复已上提 PR #400**（vllm-plugin-FL，base `release-0.2`，即 0.20.2 发布线）：
  `patch_decode_attention` 中 `alpha = scale * sqrt(head_size)`。0.20.2 双编译器
  路径验证记录（FlagTree 7/7 + triton 3.6.0 3/3）已补进 PR body。
- **Qwen3.6-27B 回归**仍未执行（见 §5），PR 合入后须补验。
