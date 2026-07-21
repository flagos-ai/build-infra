# FlagOS Release Workbook

发版操作手册。每条可直接执行，Ctrl+C 即可复制命令。

> `flaggems-builder` 每日自动推送到 `flagos-pypi-daily` 的 wheel 用于日常开发。
> 使用者在 runtime 镜像内 `pip install --index-url ...` 覆盖即可，不影响发版流程。

## 前置检查

- [ ] `gh auth status` — GitHub CLI 已认证
- [ ] 所有 base Containerfile SDK 版本无需变更

---

## 1. 更新 configs.yaml

确定目标版本号，修改 `configs.yaml`：

```yaml
version: "X.Y.Z"
```

- `flaggems` 此时**留空**。
- **此时不打 tag**。tag 在整个栈验证通过后才打。

```bash
git add configs.yaml && git commit -m "chore: bump version to X.Y.Z"
git push origin main
```

## 2. 构建 base images

> **手动触发**

```bash
gh workflow run "Base Image Build (manual)" -f backend="all" -f push="true"
```

验证方式：
```bash
# 获取 run ID
gh run list -w "Base Image Build (manual)" --limit 1 --json databaseId -q '.[0].databaseId'

# 检查所有 job 状态（替换 RUN_ID）
gh run view <RUN_ID> --json jobs -q '
  [.jobs[] | .name + " | " + .status + " | " + (.conclusion // "running")] | sort | .[]
'
```

全部 backend `completed | success` 则步骤 2 完成。

失败处理：
- **磁盘不足** — `df --output=avail /var/lib/docker | tail -1` 确认；可能需要 `docker system prune`
- **Harbor push 超时** — 检查网络，重试
- **apt/curl 网络错误** — runner 到资源服务器的连通性问题，重试

## 3. 验证 base images + 生成描述

> **手动触发**

```bash
gh workflow run "Base image descriptions"
```

工作流自动：
1. 在每个硬件 runner 上 `docker run` 对应 base 镜像 → verify → `dpkg-query` 抓系统包版本
2. `accumulate` job（ubuntu-latest）收集全部 artifact → 运行 `gen_descriptions.py`
3. 自动开出 review-gated PR

验证方式：
```bash
# 等待 accumulate job 完成，确认 PR 被开出
gh pr list --head auto/image-descriptions-*
```

- [ ] 确认所有 backend verify 通过（检查 PR 描述中无缺失标注）
- [ ] 系统包版本无意外大版本跳变（gcc、libc 等）
- [ ] Review + merge PR

合并后 `base-descriptions-publish.yml` + `hugo-site.yaml` 自动推送描述到 Harbor 和文档站。

## 4. 构建 runtime:v1（构建平台）

> **手动触发。** 产出不含 FlagGems 的运行时镜像，用于步骤 5 的 cpp wheel 编译。仅本地保存，不推 Harbor。

```bash
gh workflow run "Runtime Image Build (manual)" -f backend="all" -f push="false" -f no_flaggems="true"
```

验证方式：
```bash
gh run list -w "Runtime Image Build (manual)" --limit 1 --json databaseId -q '.[0].databaseId'
gh run view <RUN_ID> --json jobs -q '...'  # 同步骤 2
```

全部 backend `completed | success` 则步骤 4 完成。

如果只有部分 backend 需要 runtime:v1（比如只验证 nvidia），可以只触发指定 backend：
```bash
gh workflow run "Runtime Image Build (manual)" -f backend="nvidia-cuda13.3" -f no_flaggems="true"
```

## 5. FlagGems 构建 wheels

前置条件：步骤 4 全部完成（或至少目标 backend 完成）。

### 5a. 在 FlagGems 仓库打 release tag

在 FlagGems 仓库手动打 tag（如 `v5.3.1`），然后触发工作流。

### 5b. 构建 + 推送所有 wheel

> **手动触发**

```bash
gh workflow run "FlagGems Release Wheels" -f flaggems_ref="v5.3.1"
```

工作流自动：
- `python-wheel` (h20)：纯 Python wheel → 推送到全部 14 个 vendor PyPI
- `cpp-wheels` (各硬件 runner)：在本地 runtime:v1 内编译 cpp wheel → 推送到对应 vendor PyPI
- `update-config` (ubuntu-latest)：自动回填 `flaggems:` 字段 → 开 PR

### 5c. Merge PR

验证：
```bash
gh pr list --head auto/flaggems-*
```

Review + merge。

## 6. 构建 runtime:v2（正式镜像）

> **手动触发。** 基于 Harbor 上最新的 base 镜像 + PyPI 上最新的 wheel，产出最终 runtime 镜像并推 Harbor。

```bash
gh workflow run "Runtime Image Build (manual)" -f backend="all" -f push="true"
```

`flaggems` 留空 — 自动读取 `configs.yaml` 中的版本。

## 7. 验证 runtime v2（端到端）

在对应硬件的节点上手动验证：

```bash
docker pull harbor.baai.ac.cn/flagos-runtime/flagos-runtime-<vendor>-<backend>:latest
docker run --gpus all harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:latest \
  python -c "import flag_gems; ..."
```

如果验证失败：
- **包版本不兼容**：调整 `configs.yaml` → 返回步骤 4
- **FlagGems bug**：修补代码 → 重新打 tag → 返回步骤 5

## 8. 更新 runtime 描述

> **手动触发**

```bash
gh workflow run "Base image descriptions"
```

生成 runtime 页面最终版本（含 `flag_gems` 版本号）。Review + merge PR。

## 9. 打 release tag

全部验证通过后：

```bash
git checkout main && git pull
git tag -f vX.Y.Z HEAD
git push -f origin vX.Y.Z
```

tag 含义：**这个 commit 上的整套 FlagOS 软件栈（base → runtime:v1 → FlagGems → runtime:v2）已经过验证。**
