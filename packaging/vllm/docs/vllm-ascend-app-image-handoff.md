# Ascend 0.24.0 适配验证 —— app 镜像使用说明

> 本镜像为交付形态（app 镜像，wheel 单步安装线）。

## 1. 镜像位置

| 项 | 值 |
|---|---|
| 镜像 | `harbor.baai.ac.cn/flagos-dev/vllm-ascend-cann9.0.0:2.1.2` |
| 构建 | 2026-08-18，run 32146899749，已 push |
| 构建 Containerfile | [`app/vllm/Containerfile`](https://github.com/flagos-ai/build-infra/blob/main/app/vllm/Containerfile) |
| 实测节点 | Ascend 910B4，CANN 9.0.0，driver 26.0.rc1，aarch64 |

**注意**：flagos-dev 仓库是临时使用，最终发布时会使用 flagos-app 之类的仓库。

## 2. 镜像内版本指纹

- vllm `0.24.0+flagos`（cp311 aarch64 empty wheel，单步安装）
- vllm-plugin-fl `0.2.0+gcf8998c.d20260818`（vendor PyPI wheel，
  commit [`cf8998c`](https://github.com/flagos-ai/vllm-plugin-FL/commit/cf8998c4bf2c349cfafb8a66e1994517526aa650)，
  PR #387）
- torch 2.10.0+cpu / torch_npu 2.10.0 / flag_gems 5.3.4
- torchvision / torchaudio 未安装
- 编译器：默认 flagtree 0.6.1+ascend3.5
- 环境设置：`ENV VLLM_PLUGINS=fl`
- serve 指纹：`system_fingerprint: vllm-0.24.0-0535d777`

> 注：镜像内插件为 wheel 安装（release 形态）。若需迭代插件源码，请用
> runtime 镜像 editable 安装 vllm-plugin-FL（v0.3.0-dev 分支）。

## 3. 启动（实测通过的完整命令）

```bash
docker run -d --name vllm-ascend-024 \
  --device /dev/davinci0 --device /dev/davinci_manager \
  --device /dev/devmm_svm --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  -v /data/models/Qwen/Qwen3-4B:/models/Qwen3-4B \
  -p 8031:8031 \
  harbor.baai.ac.cn/flagos-dev/vllm-ascend-cann9.0.0:2.1.2 \
  vllm-serve --model /models/Qwen3-4B --port 8031 \
  --gpu-memory-utilization 0.6 --enforce-eager --trust-remote-code \
  --max-model-len 2048 --dtype bfloat16
```

- 默认 CMD = 同一参考 serve（模型路径 `/data/models/Qwen/Qwen3-4B`）；
  模型路径不同时按上面形式覆盖 CMD

## 4. 验证步骤

```bash
# 1. 等 serve 就绪
docker logs -f vllm-ascend-024   # 直到 Application startup complete

# 2. 推理（须在节点内 curl；8031 对外网不可达）
curl http://localhost:8031/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"/models/Qwen3-4B","prompt":"What is 7 times 8? Answer:","max_tokens":64}'
```

## 5. 检查点（0.24.0 ascend 适配生效的证据）

- `Block size is set to 128`（prefix cache / chunked prefill 补丁生效）
- `Patched HybridAttentionMambaModelConfig for Ascend`
- `Enabled custom fusions: norm_quant, act_quant`
- `system_fingerprint: vllm-0.24.0-0535d777`
- 推理连贯、崩溃标记 0（无 Traceback / 无挂死）

## 6. 注意事项

- `Failed to import from vllm._C` 警告是 empty wheel 的正常现象，无害。
