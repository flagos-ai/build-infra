# vllm 0.20.2 — iluvatar corex4.5.0

> 本文对应原报告第 2 部分。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 2.12 iluvatar-corex4.5.0（✅ 双编译器 E2E 通过）

**日期:** 2026-08-30　**平台:** Iluvatar CoreX BI-V150（ix23 节点）

**目标:** vllm 0.20.2 (empty) + vllm-plugin-FL 的 **app 镜像** 端到端验证，
`harbor.baai.ac.cn/flagos-app/vllm0.20.2-iluvatar-corex4.5.0:2.1.2-0.2.1_gc0c060a6.d20260827`

**结论：** F/T 双路径均 E2E 通过（flagtree 3.6.0 / vendor triton 3.2.0），
无补丁、无降级、零额外 env。

### App 镜像验证（verify-vllm-backend.sh --app-image）

`--app-image` 模式对比 runtime↔app 关键包矩阵（逐项须一致）→ vllm+vllm_fl 导入 →
真实 serve + completion：

| 检查 | F（flagtree 3.6.0） | T（vendor triton 3.2.0） |
|---|---|---|
| BEFORE/AFTER 矩阵 | torch 2.10.0+corex.4.5.0.20260804；torch_npu 无；triton 无（默认 python3 视角）；flag_gems 5.3.5；numpy 1.26.4 —— 逐项一致 | 同左 |
| vllm+vllm_fl 导入 | ✅ | ✅ |
| serve 就绪 | ~90s | ~150s |
| completion | ✅ 同文本 | ✅ 同文本 |

> 两路径 completion 同文本：`' Paris. The capital of Germany is Berlin. The capital of Italy is Rome.'`
> 单步安装零泄漏（矩阵不变），容器用后即清。

### 启动

```bash
docker run -d --network host --device /dev/iluvatar0 \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-iluvatar-corex4.5.0:2.1.2-0.2.1_gc0c060a6.d20260827
```

默认 CMD 直接 serve（app env 由镜像自带）；显式覆盖模型/参数同
[`playbook.md`](../playbook.md)。

### Stack 验证

| 组件 | 版本 |
|---|---|
| vllm | 0.20.2+flagos（app 单步安装） |
| torch | 2.10.0+corex.4.5.0.20260804（镜像自带，未降级） |
| flagtree | 3.6.0（F 默认） |
| triton | F 路径 venv 内置 3.6.0；T 路径 vendor 3.2.0（/opt/triton） |
| flag_gems | 5.3.5 |
| numpy | 1.26.4（configs.yaml pin） |
| vllm_fl | 0.2.1+gc0c060a6.d20260827（= image_tag 后缀） |

**相关提交：** app 镜像构建 + tag 记录（[build-infra #625](https://github.com/flagos-ai/build-infra/pull/625)）；F/T 验证记录（[build-infra #626](https://github.com/flagos-ai/build-infra/pull/626)）。

## 2.13 iluvatar 0.20.2 技术路线（2026-09-07 定案，corex4.5.0）

**交付镜像：** `vllm0.20.2-iluvatar-corex4.5.0:2.1.2-0.2.1_g16e8655.d20260907`（plugin `g16e8655`）。

**确定性技术路线（F/T 双路径 30/30 temp=0 确定）：**

- **flag_gems GEMM 族黑名单（`linear/mm/mm.out/addmm/addmm_/addmm.out/bmm/bmm.out`）→ 回落 native corex ixblas。**
  根因：vllm_fl `flag_gems.enable()` 把 `aten::linear` 等劫持到 flag_gems triton `linear_kernel`；该 kernel 被
  **flagtree 编译后在 live 引擎内逐次非确定**（~1-2 bf16 ulp，同输入同指针单 stream 预 sync 仍现，offline 确定），
  temp=0 长程解码在近并列采样带翻转。同源 kernel 被 vendor corex triton 编译则 bitwise 确定（== native）。
  黑名单须**整族**：native linear 降级 addmm，只排 linear 仍被劫持。GEMM native 后 **F/T 均 30/30 确定，且吞吐反超**
  （F 14.0 tok/s vs flag_gems linear 12.3；native ixblas 快于 flagtree 编译的 flag_gems kernel）。silu_and_mul 保持
  flagos（GEMM native 下不再翻）。
- **编译器差异是分水岭**：同一 flag_gems 源 kernel，flagtree 编译非确定、vendor corex triton 编译确定。上游
  hand-off：FlagGems #6054-6057（linear/mm/addmm/bmm）。
- **F/T 双路径默认零 env**。
- **已知限制（不阻塞）**：4.5.0 T 冷引擎首请求（kernel JIT 发生在请求内）在 ~token40 近并列带单次 ~1ulp 翻转
  （2/2 冷启可复现，此后逐位确定；残余 flagos op 全 native 或可消，成本未知，后做）。
