# vllm repack 验证文档

vLLM 各版本 repack（empty 构建 + `+flagos` + 单步安装）的验证记录，按版本拆目录。

## 入口

| 文档 | 内容 |
|---|---|
| [vllm-verification-matrix.md](vllm-verification-matrix.md) | 验证状态矩阵（每单元格 = 后端 × 版本 × 编译器，仅记录状态；状态块由 `scripts/render_status_matrix.py` 自动生成） |
| [vllm-0.20.2/index.md](vllm-0.20.2/index.md) | 0.20.2 版验证报告（背景、后端索引、决策） |
| [vllm-0.24.0/index.md](vllm-0.24.0/index.md) | 0.24.0 版验证报告（TL;DR、背景、metax 总览、遗留事项） |

## 各版本目录结构

```
vllm-0.X.Y/
├── index.md        # 报告入口：背景、后端索引表、版本级结论/遗留事项
├── playbook.md     # 标准流程（empty 构建 + +flagos + 单步安装）与弯路记录
├── decisions.md    # 决策：自动化边界、风险痛点、ADR、版本推进协作问题
└── backends/       # 每后端一节验证记录（nvidia/metax/mthreads/hygon/…）
```

## 伴随文档（留在顶层，跨版本引用）

- [kunlunxin-xpu-triton-attention-compiler-bug.md](kunlunxin-xpu-triton-attention-compiler-bug.md) —
  kunlunxin P800 XPU 三处 Triton attention 内核编译失败（厂商移交件）
- [kunlunxin-decode-repetition-scale-bug.md](kunlunxin-decode-repetition-scale-bug.md) —
  kunlunxin 解码乱码（scale 传参错误）
- [vllm-ascend-app-image-handoff.md](vllm-ascend-app-image-handoff.md) — ascend app 镜像使用说明
- [vllm-sunrise-app-image-handoff.md](vllm-sunrise-app-image-handoff.md) — sunrise app 镜像使用说明
