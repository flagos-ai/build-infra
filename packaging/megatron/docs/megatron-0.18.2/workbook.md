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
| nvidia-cuda12.8 | ✅/✅ | ⬜/⬜ | ✅ 通过 | on-node 复验 2026-09-26，双编译器 E2E loss 一致 |
| nvidia-cuda13.3 | ⬜/⬜ | ⬜/⬜ | ❌ | inductor 解析 flagcx `.bc` 失败（`libflagcx_device.bc` ValueError） |
| cambricon-neuware4.7.2 | ⬜/⬜ | ⬜/⬜ | ❌ | pp group 未初始化断言 |
| hygon-dtk26.04 | ✅/✅ | ⬜/⬜ | ✅ 通过 | on-node 复验 2026-09-26；hy-smi 8× HCU DTK 26.04（github node v2.1.2 过旧 → `--stack-version 2.2.0`） |
| metax-maca3.8.1.3 | ⬜/⬜ | ⬜/⬜ | ✅ 通过 | CI 走 flagtree 默认 |

CI verify = 构建时 workflow 内 pre-push 的 import check + mock-data pretrain_gpt 5 iters
（仅 flagtree 默认编译器）；**不等于 on-node 双路径复验**。

## changelog（发布授权闸门）

- 10 个 0.18.2 changelog 均已 push 记录（PR #1115/#1116/#1122/#1123-#1126 合并进 main），
  但 `2.2.0-0.3.0` 条目 **date 为空** → `changelog_gate.py` 视为 pending，**未授权发布**。
- record step 已回填 matrix `image_tag`（2.2.0-0.3.0）+ 启动页（20 个 en/zh，PR #1122/#1123-#1126）。

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
3. cuda13.3（flagcx .bc）与 cambricon（pp-group）优先诊断修复；修不了 → 下线对应镜像。
4. 验证通过的后端：回填 changelog date（授权发布）+ 更新本工作簿 + 更新 status matrix。
