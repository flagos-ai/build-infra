# Megatron 0.18.2 验证工作簿

> 0.18.2 线唯一主线：镜像构建 → on-node 验证（F/T 双路径）→ 验证通过才 push
> / record / 授权发布。**验证不过的镜像必须下线，不得留"已发布未验证"。**
> 用户 2026-09-26 定案。本文件随验证推进增量更新；与 0.17.1 分开追踪。

## 版本与制品

- wheel：`megatron-core==0.18.2+0.3.0`（无 `fl` local label），源 = MLF `v0.3.0`
  tag（`066fd5edf541`，含 [MLF #189](https://github.com/flagos-ai/Megatron-LM-FL/pull/189)
  全 scope wheel）。4 个 wheel 已上传 `flagos-pypi-{vendor}`：cp312 ×
  nvidia/metax/cambricon，cp310 × hygon。
- app 镜像 tag：`{app}0.18.2-{app_name}:2.2.0-0.3.0`，10 个已 push（见下表）。

## 已 push 镜像（tag 2.2.0-0.3.0，未验证 = 不可用）

| 后端 | app_name | training | rl |
|---|---|---|---|
| nvidia-cuda12.8 | generic-12.8 | ✅ push | ✅ push |
| nvidia-cuda13.3 | generic-13.3 | ✅ push | ✅ push |
| cambricon-neuware4.7.2 | cambricon-neuware4.7.2 | ✅ push | ✅ push |
| hygon-dtk26.04 | hygon-dtk26.04 | ✅ push | ✅ push |
| metax-maca3.8.1.3 | metax-maca3.8.1.3 | ✅ push | ✅ push |

## 验证状态（F = flagtree，T = triton；⬜ 待验 / ✅ 通过 / ❌ 失败 / ⏸ 挂起）

| 后端 | training F/T | rl F/T | CI verify（构建时） | 备注 |
|---|---|---|---|---|
| nvidia-cuda12.8 | ✅/✅ | ✅/✅ | ✅ 通过 | training 复验 2026-09-26，双编译器 E2E loss 一致；RL E2E 复验 2026-09-27（见 §RL E2E） |
| nvidia-cuda13.3 | ✅/✅ | ✅/✅ | ❌ | training 成功配方：`FLAGCX_BITCODE_PATH=/opt/flagtree/triton/backends/nvidia/lib/libflagcx_device.bc`（flagtree 自带 .bc），F/T 双路径 E2E 通过，loss 1.087099E+01 与 cuda12.8 一致；env 已固化 configs.yaml，rebuild 后默认可用（现推镜像未含 env，F 路径需显式注入）；RL E2E 复验 2026-09-27（见 §RL E2E） |
| cambricon-neuware4.7.2 | ❌/— | ⬜/— | ❌ | on-node 复现：wheel(v0.3.0) 无 MLU 平台登记 → pp group 未初始化；须按 release/0.2 重建 wheel 后复验，否则下线 |
| hygon-dtk26.04 | ✅/✅ | ⬜/⬜ | ✅ 通过 | on-node 复验 2026-09-26；hy-smi 8× HCU DTK 26.04（github node v2.1.2 过旧 → `--stack-version 2.2.0`） |
| metax-maca3.8.1.3 | ✅/✅ | ⬜/⬜ | ✅ 通过 | on-node 复验 2026-09-26，双编译器 loss 逐位一致 |

CI verify = 构建时 workflow 内 pre-push 的 import check + mock-data pretrain_gpt 5 iters
（仅 flagtree 默认编译器）；**不等于 on-node 双路径复验**。

## changelog（发布授权闸门）

- 10 个 0.18.2 changelog 均已 push 记录（PR #1115/#1116/#1122/#1123-#1126 合并进 main），
  但 `2.2.0-0.3.0` 条目 **date 为空** → `changelog_gate.py` 视为 pending，**未授权发布**。
- record step 已回填 matrix `image_tag`（2.2.0-0.3.0）+ 启动页（20 个 en/zh，PR #1122/#1123-#1126）。

## RL E2E（nvidia 0.18.2，2026-09-27）

RL 场景按 0.17.1 定案的双编译器 mock-data GRPO 配方复验
（`--transformer-impl local`，无 vendor TE），harness = 0.17.1 的
`/private/tmp/rl_harness/`（dummy_agent + env.yaml + run_rl.sh）。0.18.2 需要
两个运行时垫片（容器内改已装 wheel，不建新镜像；均未进入镜像，故镜像本身无需
改动）：

- **block size 16 → 256**：v0.3.0 的 paged KV 经 flash_attn 的
  `_flash_attn_varlen_forward`，要求 block size 为 256 的倍数
  （0.17.1 无此要求）。`--inference-dynamic-batching-block-size 256`。
- **THD packed_seq_params**：`get_logprobs` 的无 packing 分支无条件构造 THD
  `PackedSeqParams`，而 `--transformer-impl local` 的 DotProductAttention 拒绝
  packed_seq_params → GRPO 首轮 update 崩溃。release/0.2 在 local impl 下
  pass-through None；v0.3.0 丢了该分支。容器内给 `rl_utils.py:get_logprobs` 与
  `train_rl.py:forward_step` 各补一个 `elif args.transformer_impl != "local"` 守卫
  （恢复 release/0.2 行为）。这是 v0.3.0 的缺陷，待上游修复后 wheel 里不需要垫片。

实测（h20，镜像 `megatron_rl0.18.2-generic-{12.8,13.3}:2.2.0-0.3.0`，
单卡 GRPO 2 iterations × 8 rollouts，`--eval-iters 0`）：

| 后端 | 编译器 | 结果 | GRPO iteration 1 | iteration 2 |
|---|---|---|---|---|
| nvidia-cuda12.8 | F（flagtree 3.6.0） | ✅ exit 0 | lm loss 1.168E-05, kl 1.168E-02 | lm loss 1.193E-05, kl 1.193E-02 |
| nvidia-cuda12.8 | T（triton 3.6.0） | ✅ exit 0 | lm loss 1.202E-05, kl 1.203E-02 | lm loss 1.208E-05, kl 1.208E-02 |
| nvidia-cuda13.3 | F（flagtree 3.6.0） | ✅ exit 0 | lm loss 1.202E-05, kl 1.203E-02 | lm loss 1.220E-05, kl 1.221E-02 |
| nvidia-cuda13.3 | T（triton 3.6.0） | ✅ exit 0 | lm loss 1.164E-05, kl 1.164E-02 | lm loss 1.207E-05, kl 1.207E-02 |

（loss 为 GRPO 策略 update 的 lm loss，含 kl；4 格均非 0 且非 NaN，reward
确定性返回 1/0 → advantage 非退化，rollout→update 全链路通过。跑完无残留
进程，测试容器已删。）

## 节点环境

SSH 别名均经 `bastion.aiops.baai.ac.cn`（Port 2224）；Rule 22：登录后
`su -` 到非 root 账号（secure/tengqm）执行操作。镜像名均在节点本机。

| runner 标签 | 用途 | SSH 入口 | 备注 |
|---|---|---|---|
| `[self-hosted, h20]` | nvidia | `ssh h20`（登录 `secure`） | H20 cluster；`--gpus all` |
| `[self-hosted, cambricon]` | cambricon | `ssh cambricon`（root，`secure` 在 docker 组） | MLU590-M9DE 8 卡；`--device /dev/cambricon_dev0 --device /dev/cambricon_ctl` |
| hygon | hygon | `ssh hygon25`（root，`secure` 在 docker 组） | Hygon BW1000 8× HCU，DTK 26.04；kfd+mkfd 双设备 |
| metax | metax | `ssh metax124`（root，`secure`/`tengqm`） | MACA 3.8.1.3；`--device /dev/mxcd --device /dev/dri` |

## 下一步

1. 填节点 SSH 入口（从 build-config.yml runners / 既有 memory 查）。
2. 逐后端 on-node 复验：`packaging/megatron/verify/verify-megatron-backend.sh <backend>
   --app-image <tag> --megatron-version 0.18.2+0.3.0 --compiler <flagtree|triton>`，
   training + rl 双场景 × 双编译器。
3. nvidia RL E2E 双路径已过（2026-09-27，见 §RL E2E）；cuda13.3 training 成功配方
   已定（env 固化，待 rebuild）；cambricon 诊断完毕（wheel 无 MLU 登记）、
   按 release/0.2 重建 wheel 后复验；修不了 → 下线对应镜像。
4. 验证通过的后端：回填 changelog date（授权发布）+ 更新本工作簿 + 更新 status matrix。
