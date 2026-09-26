# Megatron-LM-FL 0.18.2 验证报告

> 0.18.2 这条线与 0.17.1 分开追踪（用户 2026-09-26 指定），勿并入
> [../megatron-0.17.1/index.md](../megatron-0.17.1/index.md)。

## 背景

0.18.2 app 线 = runtime 镜像 + `megatron-core[training|rl]==0.18.2+0.3.0`
单步安装（不 `--no-deps`）。wheel 从 [Megatron-LM-FL](https://github.com/flagos-ai/Megatron-LM-FL)
fork 的 `v0.3.0` tag（`066fd5edf541`，HEAD = 0.3.0-rc2）构建，**无 `fl` local
label**——版本号就是 `0.18.2+0.3.0`（用户明示，不要 `fl`）。`v0.3.0` 已含
[MLF #189](https://github.com/flagos-ai/Megatron-LM-FL/pull/189) 全 scope wheel
（7 子包 + 9 入口模块，含 `pretrain_gpt`）。

## wheel 产物（4 个，均已上传 `flagos-pypi-{vendor}`）

| 后端 | Python | wheel `0.18.2+0.3.0` |
|---|---|---|
| nvidia-cuda12.8 / 13.3 | cp312 | ✅ |
| metax-maca3.8.1.3 | cp312 | ✅ |
| cambricon-neuware4.7.2 | cp312 | ✅ |
| hygon-dtk26.04 | cp310 | ✅ |

`megatron-core` 带编译扩展 `helpers_cpp`（pybind11），CPython-ABI 特定，按 runtime
矩阵的 Python 版本各构建一个。构建环境 = 后端 runtime 镜像本身，ABI 契约按构造匹配。

## 第一批构建 / 验证轮（2026-09-26）

第一批后端：nvidia-cuda12.8 / nvidia-cuda13.3 / hygon-dtk26.04 / metax-maca3.8.1.3 /
cambricon-neuware4.7.2。app 镜像 tag `2.2.0-0.3.0`，5 行（training + rl）全量
`push=true` 构建。

| 后端 | training-app | rl-app | 验证结论 |
|---|---|---|---|
| nvidia-cuda12.8 | generic-12.8 | generic-12.8 | ✅ E2E training（lm loss ~1.087）|
| hygon-dtk26.04 | hygon-dtk26.04 | hygon-dtk26.04 | ✅ E2E training（~1.089）|
| metax-maca3.8.1.3 | metax-maca3.8.1.3 | metax-maca3.8.1.3 | ✅ E2E training（~1.088）|
| nvidia-cuda13.3 | generic-13.3 | generic-13.3 | ❌ flagcx `.bc` 解析失败（见下）|
| cambricon-neuware4.7.2 | cambricon-neuware4.7.2 | cambricon-neuware4.7.2 | ❌ pp group 未初始化（见下）|

10 个 app 镜像均已 **push**（push 不因 verify 失败而跳过）。其中 6 个 verify 通过
（nvidia-cuda12.8 / hygon / metax × training/rl，E2E pretrain_gpt 5 iters，loss 收敛
~1.087~1.089）；2 个后端 × 2 个 app 的 verify 失败。

### 未闭环的 verify 失败

- **nvidia-cuda13.3（flagtree 默认路径，torch 2.11.0+cu130）**：Triton 编译
  `triton_poi_fused_add_mul_tanh_0` 时，inductor `parse_library` 在
  `/flagos/lib/python3.12/site-packages/flagcx/lib/libflagcx_device.bc` 失败
  `ValueError: Failed to parse library`。cuda12.8（torch 2.10.0+cu128）同路径通过。
  疑为 cuda13.3 runtime 里 flagcx 的 `.bc` 设备库与 torch 2.11 inductor 期望的
  格式不匹配（相对 0.17.1 的 inductor 处理方案，见
  [../megatron-0.17.1/backends/nvidia.md](../megatron-0.17.1/backends/nvidia.md)）。
- **cambricon-neuware4.7.2**：wheel 内 `_set_random_seed → get_pipeline_model_parallel_group`
  断言 `pipeline_model parallel group is not initialized`。源码分析确认 pp 组在
  `initialize_model_parallel` 中对 pp=1 也是无条件构建，`para_ctx` 标准路径恒为
  `None`（`set_parallel_context` 无调用者）。疑 cambricon 的 torch-distributed/CNCL
  初始化影响了 `new_group`。需在已 push 的 app 镜像内 on-node 复现。

## 遗留

- **record 回填**：第一批 6 个通过 verify 的镜像（3 后端 × training/rl）Record step
  因 status matrix 尚未上 main 而失败（run 36212107759 / 36212109803）。PR #1118 合并后
  重跑（push 幂等）或本地跑 `record_app_image_tag.py`，回填 changelog date + image_tag。
- **cambricon + cuda13.3 verify 未闭环**（见上）。
- **旧 wheel 清理**：`flagos-pypi-hygon` 上残留 `megatron_core-0.18.2+fl.0.3.0rc2-cp310`
  （迁移前的 0.3.0-rc2 制品，缺 #189），待删除。
- **F/T 双路径**：CI verify 走 runtime 默认编译器（flagtree）。按纪律每后端另跑
  T（triton）路径 on-node 复验后，`backends/` 逐后端记录再补齐。
- **app_public 命名**：nvidia 双后端以 app 层公开名发布（generic-12.8 / generic-13.3），
  base/runtime/矩阵键仍用真实名 nvidia-cuda12.8/13.3。