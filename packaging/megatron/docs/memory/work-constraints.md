---
name: work-constraints
description: 用户反复强调的工作约束——报告语言、禁止事项、操作纪律、PR 规范
metadata:
  type: feedback
---

# 工作约束（用户明确要求，持续有效）

## 报告与交流

- 报告用**精确的中文技术语言**，只记录**可复现**的发现（代码级缺陷、未声明依赖、平台移植性、工具链限制），不记录瞬时错误/一次性环境故障。
- 文字要**压缩**：用户"你刷了一屏又一屏的文字，我把前面的事项又忘了"——输出要短、面向决策点。
- 先讲清楚再干活：用户"你又急着干活，先把事情讲清楚。决策点说清楚"。
- 报告命名不要自造晦涩术语（如 PART A/B），用用户能直接看懂的名称（wheel-only 训练循环 / 完整训练服务）。
- 用户对报告措辞敏感：不准确就纠正（如"上游"歧义、"psutil 是我们引入的吧"→ 实为 NVIDIA 上游代码、本 fork 继承）。改报告前先核对证据。

## 操作纪律

- 节点上**绝不用 root**（用 `secure` 账户）。
- **绝不用 `--no-deps`** 做实验。
- rule 12：**节点清理前必须先问**。
- rule 13：**不做单方面设计决策**——所有设计决策先摆给用户。
- rule 15：改代码前**先同步上游 main**。

## PR 规范（提交到 flagos-ai/Megatron-LM-FL）

- PR body 结尾："This PR was written in part with the assistance of generative AI."
- **不写** Co-Authored-By、无其他 trailer、不提工具名。

## 术语约定

- "上游"两级：**代码来源 = NVIDIA ADLR/Megatron-LM**；**提交/反馈目标 = 本 fork flagos-ai/Megatron-LM-FL**。
- "我们"指 **megatron-lm-fl（本 fork）**，不是 NVIDIA。

## 记忆生命周期

- **项目做完后删除 memory 目录**（`packaging/megatron/docs/memory/`），不留残余——避免占用 context、白耗 token，用户不用回头清。
- 删除前确认项目确实收尾（任务全 closed）。

## 相关

- [[megatron-verification-state]]、[[hygon-compiler-mask]]
