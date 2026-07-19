# FlagOS Release Workbook

发版操作手册。每条一个 checkbox，逐项执行。

> `flaggems-builder` 每日自动推送到 `flagos-pypi-daily` 的 wheel 用于开发/测试：
> 使用者拉取 runtime 镜像后，手动从 `flagos-pypi-daily` 安装 daily wheel 覆盖镜像内
> 的 release 版本即可开始测试。这些 daily wheel 不是发版流程的一部分。

## 前置检查

- [ ] 所有 base Containerfile 的 SDK 版本无需变更（本次 release 不涉及 SDK 升级则跳过）

## 1. 更新 configs.yaml（版本声明）

确定目标版本号，修改 `version:`：

```yaml
version: "2.2.0"
```

注意：
- `flaggems` 此时留空，base image 构建不依赖 FlagGems 版本。
- **此时不打 tag**。`version:` 只是声明"我们打算发布 `2.2.0`"；
  `scripts/version.py` 在 tag 不存在时返回纯版本号（不含 `-n`），
  构建不受影响。tag 在整个栈验证通过后才打。

提交并 push 到 main。

## 2. 构建 base images

GitHub Actions → **Base Image Build (manual)** → `backend: all`, `push: true`。

确认全部 backend 构建成功并推送到 Harbor。

## 3. 验证 base images + 生成描述

### 3a. 验证

构建完成的 base image 需要在有对应硬件的节点上逐一验证。

1. 在目标硬件节点上 `docker pull` 对应 vendor 的 base image
2. 运行 `build-config.yml` 中 `verify:` 定义的验证命令，确认加速器可见
3. 如果验证失败，修复 Containerfile 后回到步骤 2 重建

验证命令速查（详见 `build-config.yml` `verify.vendors`）：

| Vendor | Verify 命令 |
|---|---|
| nvidia | `nvidia-smi` |
| ascend | `source /usr/local/Ascend/ascend-toolkit/set_env.sh && npu-smi info` |
| metax | `mx-smi` |
| cambricon | `cnmon` |
| iluvatar | `ixsmi` |
| hygon | `source /opt/hyhal/env.sh && hy-smi` |
| kunlunxin | `xpu-smi` |
| mthreads | `mthreads-gmi` |
| enflame | `efsmi` |
| sunrise | `pt_smi` |
| tsingmicro | `tsm_smi` |

### 3b. 生成描述

验证通过后，触发 **Base image descriptions** workflow (dispatch)。验证节点上镜像已就绪，
直接提取系统包版本并生成描述，打开 **review-gated PR**。

Base image 线自此结束——后续不再修改 Containerfile。

## 4. 审核描述 PR

- [ ] 确认版本号正确
- [ ] 系统包版本无意外大版本跳变（gcc、libc 等）
- [ ] 所有 backend 的描述均已生成

Merge PR。合并后 **base-descriptions-publish.yml** 自动将描述推到 Harbor。

## 5. FlagGems 打 tag + 构建 release wheels

### 5a. 构建 Python wheel

1. 在 FlagGems 仓库打 release tag（如 `v5.4.0`）
2. 使用该 tag 构建纯 Python wheel：`flag_gems-x.y.z-py3-none-any.whl`
   — 不依赖 vendor SDK，任意环境可构建
3. 验证：`pip install flag_gems==5.4.0 && python -c "import flag_gems"`，确认包无损坏
4. 将 Python wheel 推送到**所有** vendor 的 PyPI：`flagos-pypi-<vendor>`

### 5b. 构建 cpp operator wheels

对每个有 `cmake_backend` 的 vendor（nvidia / ascend / mthreads / enflame / iluvatar），
使用该 vendor 的 base image 构建 `flag_gems_cpp_<vendor>-x.y.z-*.whl`。

构建完成后，在同一 base image 中验证 cpp 算子可用：
`pip install flag_gems[cpp-<vendor>]==5.4.0 && python -c "import flag_gems; flag_gems.test_cpp_extension()"`，
确认至少一个 C++ 算子可正常调用并返回正确结果。

验证通过后推送到对应的 `flagos-pypi-<vendor>`。

没有 `cmake_backend` 的 vendor 跳过此步骤，其 runtime image 使用 5a 推送的 Python wheel。

### 5c. 回填版本号

构建完成后，**更新 configs.yaml 中的 `flaggems` 字段**：

```yaml
flaggems: "5.4.0"
```

提交并 push。

## 6. 构建 runtime images

### 6a. 确认依赖版本

检查 `configs.yaml` 中所有 backend 的 `deps:` / `flagtree:` / `triton:` 版本是否为目标版本。
`torch` 与 `flagtree`/`triton`、`torch` 与 `triton_post_install` 之间的版本匹配是高风险点——
运行时会首次将这些包在同一 venv 中组装，兼容性问题在这里暴露。

### 6b. CI 构建

GitHub Actions → **Runtime Image Build (manual)**：

- `backend: all`
- `push: true`
- `flaggems: 5.4.0`（与 `configs.yaml` 一致，留空则使用 `configs.yaml` 值）

Runtime image 从 `flagos-pypi-<vendor>` 安装步骤 5 推送的 release wheel。

### 6c. 验证 runtime images

构建并推送到 Harbor 后，在有对应硬件的节点上：

1. `docker pull` runtime image
2. 运行 `python tools/run_tests.py` 确认端到端可用

如果验证失败，根据错误类型回退：

- **包版本不兼容**（`torch` / `flagtree` / `triton` 版本冲突）：调整 `configs.yaml` 中
  对应 backend 的 `deps:` / `flagtree:` / `triton:` 版本，返回**步骤 6a**。
- **FlagGems 本身存在 bug**：修补 FlagGems 代码 → 重新打 tag（如 `v5.4.1`）→ 返回
  **步骤 5** 重新构建 wheels。

> TODO: FlagGems 仓库的 `tools/run_tests.py` 脚本需要打包到 runtime 镜像中。
> 测试文件和 benchmarks 已随 `flaggems_test` / `flaggems_benchmark` 路径安装，
> 脚本到位后验证命令即统一为 `python tools/run_tests.py`，无需 per-vendor 定制。

## 7. 更新 runtime 描述

Runtime 验证通过后，`flaggems` 版本刚确定，需要刷一遍 runtime 页面的描述。

触发 **Base image descriptions** workflow (dispatch)，重新运行 `gen_data.py` +
`gen_descriptions.py`，生成 runtime 页面的最终版本（含 `flag_gems` 版本号等）。
与步骤 3b/4 一样，打开 review-gated PR，审核后 merge。

合并后 **hugo-site.yaml** 和 **base-descriptions-publish.yml** 自动触发：
- 文档站部署到 `flagos-ai.github.io/release-info`
- Runtime 描述推到 Harbor

## 8. App 镜像（TODO）

> 此步骤待 `app/` 构建系统落地后补全。App 镜像在 runtime 的基础上部署：
> - vllm + vllm-plugin-FL（推理）
> - sglang + sglang-plugin-FL（推理）
> - Megatron-LM-FL + 依赖（训练）
>
> 核心技术挑战：安装 vllm/sglang 等上层包时，必须确保不覆盖 runtime 层已锁定版本的
> torch / flagtree / triton / flag_gems 等依赖。此项将单独设计。

## 9. 打 build-infra tag

全部验证通过后，在此 commit 上打 tag：

```bash
git checkout main && git pull
git tag -f v2.2.0 HEAD
git push -f origin v2.2.0
```

tag 的含义：**这个 commit 上的整套 FlagOS 软件栈（base images → FlagGems → runtime images）
已经过验证，可以发布。** 之后如有 Containerfile 变更，`image_version()` 会从该 tag 开始自动
产生 `2.2.0-1`、`2.2.0-2` ……
