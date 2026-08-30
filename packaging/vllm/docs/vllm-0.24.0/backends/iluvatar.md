# vllm 0.24.0 — iluvatar corex4.5.0

> 本文对应 0.20.2 线 [§2.5 / §2.12](../vllm-0.20.2/backends/iluvatar.md) 的 0.24.0 延续。
> 0.24.0 仅验证 corex4.5.0（4.4.0 工具链过旧，见 0.20.2 [§2.5](../vllm-0.20.2/backends/iluvatar.md)）。
> 标准流程见 [`playbook.md`](../playbook.md)，决策见 [`decisions.md`](../decisions.md)。

## 14. iluvatar（COREX 4.5.0）详细记录（2026-08-30）

**平台:** Iluvatar CoreX BI-V150（ix23 节点）　**CoreX:** 4.5.0

**目标:** vllm 0.24.0 (empty) + vllm-plugin-FL 的 **app 镜像**端到端验证，
`harbor.baai.ac.cn/flagos-app/vllm0.24.0-iluvatar-corex4.5.0:2.1.2-0.2.1_g07063fd.d20260828`

**结论：** F/T 双路径均 E2E 通过。0.20.2 线 4.4.0 的乱码负结果由工具链解除
（4.5.0 `torch 2.10.0+corex.4.5.0.20260804`，无需任何补丁/降级/额外 env）——
本次 0.24.0 无阻塞点，一次通过。

### 14.1 App 镜像验证（verify-vllm-backend.sh --app-image）

`--app-image` 模式对比 runtime↔app 关键包矩阵（逐项须一致）→ vllm+vllm_fl 导入 →
真实 serve + completion：

| 检查 | F（flagtree 0.6.1+iluvatar3.6 → 3.6.0） | T（vendor triton 3.2.0） |
|---|---|---|
| BEFORE/AFTER 矩阵 | torch 2.10.0+corex.4.5.0.20260804；triton 无；flag_gems 5.3.5；numpy 1.26.4 —— 逐项一致 | 同左 |
| vllm+vllm_fl 导入 | ✅ `vllm 0.24.0 \| plugin ok` | ✅ 同左 |
| serve 就绪 | ~90s | ~150s |
| completion | ✅ 同文本 | ✅ 同文本 |

> 两路径 completion 同文本：`' Paris. The capital of Germany is Berlin.
> The capital of Italy is Rome.'`（prompt `The capital of France is`，
> max_tokens 16，temp 0）。triton 在默认 python3 视角下无（位于 /opt/triton）。
> 单步安装零泄漏（矩阵不变），容器用后即清。

### 14.2 启动

```bash
docker run -d --network host --device /dev/iluvatar0 \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-iluvatar-corex4.5.0:2.1.2-0.2.1_g07063fd.d20260828
```

默认 CMD 直接 serve（`vllm-serve --model /data/models/Qwen3-4B --port 8031
--gpu-memory-utilization 0.6 --enforce-eager --trust-remote-code
--max-model-len 2048 --dtype bfloat16`，app env 由镜像自带 `VLLM_PLUGINS=fl`）；
显式覆盖模型/参数同 [`playbook.md`](../playbook.md)。

### 14.3 Stack 验证

| 组件 | 版本 |
|---|---|
| vllm | 0.24.0+flagos（cp312 empty wheel，app 单步安装） |
| vllm_fl | 0.2.1+g07063fd.d20260828（vllm-plugin-FL main @ 07063fd7b6ed12c，= image_tag 后缀） |
| torch | 2.10.0+corex.4.5.0.20260804（镜像自带，未降级） |
| flagtree | 0.6.1+iluvatar3.6（F 默认，运行时 3.6.0） |
| triton | T 路径 vendor 3.2.0（/opt/triton） |
| flag_gems | 5.3.5 |
| numpy | 1.26.4（configs.yaml pin） |
| python | 3.12 |

**相关提交：** 镜像构建 + tag 记录（PR #628 记录 image_tag）；F/T 验证记录
（状态矩阵 PR #629）。
