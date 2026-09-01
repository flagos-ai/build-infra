# Sunrise 0.20.2 适配验证 —— app 镜像使用说明

> 本镜像为交付形态（app 镜像，wheel 单步安装线）。
>
> 相关记录见 [vllm-0.20.2/backends/sunrise.md](vllm-0.20.2/backends/sunrise.md) 与
> [`vllm-verification-matrix.md`](vllm-verification-matrix.md)（sunrise 行）。

## 1. 镜像位置

| 项 | 值 |
|---|---|
| 镜像 | `harbor.baai.ac.cn/flagos-app/vllm0.20.2-sunrise-tangrt1.2.0:2.1.2-0.2.0_g687217a.d20260819` |
| 构建 | 2026-08-20，run 32324401286，已 push |
| 构建 Containerfile | [`app/vllm/Containerfile`](https://github.com/flagos-ai/build-infra/blob/main/app/vllm/Containerfile) |
| 实测节点 | sunrise（曦望，PTPU，TANGRT 1.2.0，tang 0.24.0） |

## 2. 镜像内版本指纹

- vllm `0.20.2+flagos`（py3-none-any 纯 Python empty wheel，单步安装；
  2026-08-20 重建，run 32323105369，上传 flagos-pypi-sunrise）
- vllm-plugin-fl `0.2.0+g687217a.d20260819`（vendor PyPI wheel，commit
  [`687217a`](https://github.com/flagos-ai/vllm-plugin-FL/commit/687217afad5d64289bb5c374ad6a671b645db523)，
  [VPF #391](https://github.com/flagos-ai/vllm-plugin-FL/pull/391)）
- Python 3.10.20
- torch 2.11.0+cpu / torch_ptpu 0.2.3+torch2.11 / flag_gems 5.3.4 /
  numpy 2.2.6
- 编译器：默认 flagtree 0.6.0+sunrise3.6（rebuilt wheel 已烘焙，
  `/opt/flagtree/triton/_C/libtriton.so` md5 `924b1c0d`）；triton
  3.6.0.1+git0a5cfb35（`/opt/triton`）
- 环境设置：`ENV VLLM_PLUGINS=fl`

> 注：镜像内插件为 wheel 安装（release 形态，[VPF #391](https://github.com/flagos-ai/vllm-plugin-FL/pull/391) 分支）。若需迭代插件
> 源码，请用 runtime 镜像 editable 安装 vllm-plugin-FL（v0.3.0-dev 分支）。

## 3. 启动（实测通过的完整命令）

```bash
docker run -d --name vllm-sunrise-020 \
  --privileged -v /dev:/dev \
  -v /data/nmodels:/data/nmodels:ro \
  -p 8031:8031 \
  harbor.baai.ac.cn/flagos-app/vllm0.20.2-sunrise-tangrt1.2.0:2.1.2-0.2.0_g687217a.d20260819 \
  vllm-serve --model /data/nmodels/Qwen3-8B --port 8031 \
  --gpu-memory-utilization 0.6 --enforce-eager --trust-remote-code \
  --max-model-len 2048 --dtype bfloat16
```

- 默认 CMD = 同一参考 serve（模型路径 `/data/models/Qwen/Qwen3-4B`）；
  sunrise 节点无该路径，必须覆盖为 `/data/nmodels/Qwen3-8B`

## 4. 验证步骤

```bash
# 1. 等 serve 就绪
docker logs -f vllm-sunrise-020   # 直到 Application startup complete

# 2. 推理（须在节点内 curl；8031 未对公网开放）
curl http://localhost:8031/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"/data/nmodels/Qwen3-8B","prompt":"What is the capital of France? Answer:","max_tokens":64}'
```

> 注：app 镜像自身只完成 import 级 verify（见 §5），以下 serve 步骤在
> runtime 容器复测中实测通过，供 reviewer 对 app 镜像复跑；插件形态差异
> 见 §5 末尾说明。

## 5. 检查点（0.20.2 sunrise 适配生效的证据）

**FlagTree decode-hang 修复复测（0.20.2 环境内，2026-08-20）**

- 门禁：`/opt/flagtree/triton/_C/libtriton.so` md5 `924b1c0d`
  （[FlagTree #978](https://github.com/flagos-ai/FlagTree/pull/978) 修复 +
  rebuilt wheel 烘焙进 runtime 2.1.2）
- A/B：decode 0.4 → 2.4 tok/s（修复前挂死，修复后正常终止）
- serve `/data/nmodels/Qwen3-8B` 达 `Application startup complete`；推理
  连贯（knowledge "Paris..." / math "56"）；decode 正常终止（2 请求均
  `finish_reason=length`，无挂死）；崩溃标记 0
- 矩阵 `0.20.2(F)` 格 ❌→✅

**app-image verify（import 级门禁，run 32324401286）**

- BEFORE / AFTER critical matrix（torch / torch_ptpu / triton /
  flag_gems）一致
- `import vllm`、`import vllm_fl` 通过
- 证明 [VPF #391](https://github.com/flagos-ai/vllm-plugin-FL/pull/391) 分支
  plugin（CUSTOM 注册形态）在 0.20.2 下可 import ——
  0.24.0 移植的回归证据

> 如实说明：serve E2E 复测在 runtime 容器内进行，插件为 vllm-plugin-FL
> main（0.20.2 原生形态，`get_name()`="TRITON_ATTN"，editable 安装）；
> app 镜像内插件为 [VPF #391](https://github.com/flagos-ai/vllm-plugin-FL/pull/391)
> 分支 wheel（CUSTOM 形态，
> `get_name()`="CUSTOM"）。CUSTOM 注册是 0.24.0 移植的核心改动，app-image
> 的 import 级验证证明其在 0.20.2 下注册可用；serve 级回归证据见
> [vllm-0.24.0/backends/sunrise.md](vllm-0.24.0/backends/sunrise.md)。

## 6. 注意事项

- `Failed to import from vllm._C` 警告是 empty wheel 的正常现象，无害。
- sunrise 节点无 Qwen3-4B 模型，serve 用 `/data/nmodels/Qwen3-8B`
  （矩阵"Qwen3-4B"约定在此格不适用）。
- F 路径依赖 rebuilt flagtree wheel（md5 `924b1c0d`）；若镜像未烘焙该
  wheel，FlagTree flash-attn decode 会挂死（根因见
  [vllm-0.20.2 §2.9](vllm-0.20.2/backends/sunrise.md)）。
