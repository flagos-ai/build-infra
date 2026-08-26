# sglang-plugin-FL 打包调研

入口文档。

| 文档 | 内容 |
|---|---|
| [sglang-release-packaging-research.md](sglang-release-packaging-research.md) | sglang-plugin-FL 打包成发布镜像的调研：与 vllm-plugin-FL 的对比、仓库结构、各后端 CI 镜像版本矩阵、打包模型分析与待决策 |

## 结论速览

- **plugin 层**：与 vllm-plugin-FL 同构（OOT plugin + 运行时单步安装），成本低。
- **应用层**：与 vllm 完全不同。sglang 每后端锁死一套
  `sglang × sgl-kernel × torch × python` 四元组，且核心性能件
  （sgl-kernel / FlagCX）需要 vendor 镜像或 source 构建；build-infra 统一
  runtime 的 torch 版本除 nvidia-cuda13.3 外全部对不上。
- **结论**：发布镜像 = 每后端独立镜像线（vllm-plugin-FL `docker/build.sh`
  模式），不是 build-infra "runtime + 单步安装" 模式。是否立项是策略决策，
  本文只给事实与选项。

状态：调研完成（2026-08-26），未立项。待决策见研究文档 §6。
