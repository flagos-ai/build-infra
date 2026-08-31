# Megatron-LM-FL iluvatar E2E 验证记录

## iluvatar-corex4.4.0（2026-08-31）

验证在 ix15（Iluvatar CoreX 节点，`ssh ix15`，user `tengqm`——docker 组含
tengqm + secure）上进行，**device 2**（`IX_VISIBLE_DEVICES=2`，避开 0 号与
镜像制作冲突）。runtime 镜像 `flagos-runtime-iluvatar-corex4.4.0:2.1.2`，
Python 3.12，torch 2.7.1+corex.4.4.0，flagtree 0.6.1+iluvatar3.6（内带
triton 3.6.0），triton 3.1.0+corex.4.4.0（/opt/triton），flag_gems 5.3.4。
megatron-core 安装形态为 `packaging/megatron/builder/` 打包产出的 wheel，
`pip install` 单步安装（无 `--no-deps`）。验证周期 2026-08-31。

**结论：** training 场景双编译器（flagtree / triton）一次通过、零 triage、
零 workaround。mock-data `pretrain_gpt.py` 5 iters 双路径均 exit 0，
snapshot 矩阵前后逐项相等，`helpers_cpp` 3 callable 绑定 OK。

| 场景 | 状态 | 一句话事实 |
|---|---|---|
| training | ✅ 通过 | 双编译器直跑 `pretrain_gpt.py` exit 0；F/T loss 完全一致 |
| post_training | ? 未验证 | — |
| inference | ⛔ 挂起 | 同矩阵其余未验后端（上游阻塞） |
| rl | ⛔ 挂起 | 上游阻塞（MLF #116） |

**loss 一致性：** flagtree 与 triton 两路径 test-set validation loss 均为
1.087055E+01（F=T 完全一致），与 4.5.0 兄弟记录（1.087054E+01）同数量级。

**教训清单：**

1. **ix15 节点容器操作需 `su - tengqm`**——docker 组含 tengqm + secure
   （沿用 build-infra 规则 22）；4.4.0 线无新增平台陷阱。
2. **核心差异 vs 4.5.0**：torch 2.7.1（4.5.0 为 2.10.0）、flagtree 0.6.1
   内带 triton 3.6.0；flag_gems 5.3.4（4.5.0 为 5.3.5）。均零 workaround。

---

## iluvatar-corex4.5.0（2026-08-31）

验证在 ix23（Iluvatar CoreX BI-V150 节点，`ssh ix23`，user `tengqm`——该
节点唯一有 docker 权限的非 root 用户）上进行，runtime 镜像
`flagos-runtime-iluvatar-corex4.5.0:2.1.2`，Python 3.12，torch
2.10.0+corex.4.5.0.20260804，flagtree 0.6.1+iluvatar3.6，triton
3.2.0+corex.4.5.0.20260804（/opt/triton），flag_gems 5.3.5，numpy 1.26.4。
megatron-core 安装形态为 `packaging/megatron/builder/` 打包产出的 wheel，
`pip install` 单步安装（无 `--no-deps`）。验证周期 2026-08-31。

本报告只记录**可复现的技术发现与缺口**，不含瞬时错误与一次性环境故障。

## 0. Summary

**结论：** training 场景双编译器（flagtree / triton）一次通过、零 triage、
零 workaround。mock-data `pretrain_gpt.py` 5 iters 双路径均 exit 0，
snapshot 矩阵（torch / triton / flag_gems / numpy）前后逐项相等，
`helpers_cpp` 绑定 OK。

| 场景 | 状态 | 一句话事实 |
|---|---|---|
| training | ✅ 通过 | 双编译器直跑 `pretrain_gpt.py` exit 0；F/T loss 完全一致 |
| post_training | ? 未验证 | — |
| inference | ⛔ 挂起 | 同矩阵其余未验后端（上游阻塞） |
| rl | ⛔ 挂起 | 上游阻塞（MLF #116） |

**loss 一致性：** flagtree 与 triton 两路径 test-set validation loss 均为
1.087054E+01（F=T 完全一致）。

**教训清单：**

1. **ix23 节点 docker 权限只对 `tengqm` 开放**——secure / caoyong 均无
   docker 组权限，`su - tengqm` 后执行容器操作（沿用 build-infra 规则 22）。
2. 运行时栈与 vllm 线一致（同 torch 2.10.0+corex.4.5.0 / triton 3.2.0）；
   megatron training 在 corex4.5.0 上无新增平台陷阱。
