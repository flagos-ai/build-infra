# FlagOS Release Workbook

发版操作手册。每条可直接执行，Ctrl+C 即可复制命令。

> `packaging/flaggems` 每日自动推送到 `flagos-pypi-daily` 的 wheel 用于日常开发。
> 使用者在 runtime 镜像内 `pip install --index-url ...` 覆盖即可，不影响发版流程。
>
> FlagTree 同样有一条每日线（`flagtree-wheel-daily.yml`），每个后端一个发行名
> （`flagtree-nvidia`、`flagtree-metax`、`flagtree-enflame`、
> `flagtree-ascend-cann9.0.0` …），推送到 `flagos-pypi-daily`，版本形如
> `0.7.1.dev20261015`（只有日期，无 local 段）；`pip install --pre flagtree-nvidia`
> 即取最新。构建所用的 commit
> 不在版本号里，而在 wheel 元数据中：`pip show -v flagtree-nvidia` 会打印
> `Project-URL: Source-Commit, https://github.com/flagos-ai/flagtree/commit/<sha8>`。
> 它与发版线（`flagtree-wheel.yml` → 各 vendor index 的 `flagtree`）
> 互不影响。

## 前置检查

- [ ] `gh auth status` — GitHub CLI 已认证
- [ ] 所有 base Containerfile SDK 版本无需变更

---

## 1. 更新 configs.yaml

确定目标版本号，修改 `configs.yaml`：

```yaml
version: "X.Y.Z"
```

- `flaggems` 这一步**不要留空**：沿用上一版的值即可，`runtime-image.yml` 会把它
  当 `flag_gems==<ver>` 去装，空值会让 runtime 构建直接失败。新版本由步骤 5c 的
  PR 回填。
- **此时不打 tag**。tag 在整个栈验证通过后才打。

```bash
git add configs.yaml && git commit -m "chore: bump version to X.Y.Z"
git push origin main
```

## 2. 构建 base images

> **手动触发**

```bash
gh workflow run base-image.yml -f backend="all" -f push="true"
```

验证方式：
```bash
# 获取 run ID
gh run list -w base-image.yml --limit 1 --json databaseId -q '.[0].databaseId'

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
gh workflow run gendoc-base.yml
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

合并后 `base-descriptions-publish.yml` + `hugo-site.yml` 自动推送描述到 Harbor 和文档站。

## 4. 构建 runtime 镜像（cpp wheel 的构建平台）

> **手动触发。** 推到 Harbor，供步骤 5 的 cpp wheel 编译拉取。

```bash
gh workflow run runtime-image.yml -f backend="all" -f push="true"
```

镜像 tag: `:{version}`（如 `:2.2.0`）。此时 configs.yaml 的 `flaggems:` 还是上一版，
没关系：这一步要的是**构建环境**（torch + deps + 编译器齐备），
flag_gems 版本在步骤 6 重建时才对齐。

**这次 push 同样要过 changelog 门禁** —— `runtime/changelogs/<backend>.yaml` 里先写一条
待定条目，说明为什么现在重建（新建 tag / deps 变更 / **构建平台**）。见 `docs/changelog.md`。

验证方式：
```bash
gh run list -w runtime-image.yml --limit 1 --json databaseId -q '.[0].databaseId'
gh run view <RUN_ID> --json jobs -q '...'  # 同步骤 2
```

全部 backend `completed | success` 则步骤 4 完成。

如果只有部分 backend 需要（比如只验证 nvidia），可以只触发指定 backend：
```bash
gh workflow run runtime-image.yml -f backend="nvidia-cuda13.3"
gh workflow run runtime-image.yml -f backend="nvidia-cuda13.3" -f push="true"
```

## 5. FlagGems 构建 wheels

前置条件：步骤 4 全部完成（或至少目标 backend 完成）—— cpp wheel 在步骤 4 推上去的 runtime 镜像内编译。

### 5a. 在 FlagGems 仓库打 release tag

在 FlagGems 仓库手动打 tag（如 `v5.3.1`），然后触发工作流。

### 5b. 构建 + 推送所有 wheel

> **手动触发**

```bash
gh workflow run flaggems-release.yml -f flaggems_ref="v5.3.1"
```

工作流自动：
- `python-wheel` (h20)：纯 Python wheel → 推送到全部 14 个 vendor PyPI
- `cpp-wheels` (各硬件 runner)：在本地 runtime 镜像内编译 cpp wheel → 推送到对应 vendor PyPI
- `update-config` (ubuntu-latest)：自动回填 `flaggems:` 字段 → 开 PR

### 5c. Merge PR

验证：
```bash
gh pr list --head auto/flaggems-*
```

Review + merge。

## 6. 重建 runtime 镜像（正式交付镜像）

> **手动触发。** 步骤 5c 的 PR 合并后，`configs.yaml` 的 `flaggems:` 已是新版本，
> 重建一次让交付镜像带上它。基于 Harbor 上最新的 base 镜像 + PyPI 上最新的 wheel。

```bash
gh workflow run runtime-image.yml -f backend="all" -f push="true"
```

`flaggems` 留空 — 自动读取 `configs.yaml` 中的版本。

镜像 tag: `:{version}`（如 `:2.2.0`）—— 与步骤 4 同一个 tag，覆盖它（flat tag 的既定发布模型）。
同样要过 changelog 门禁：这次的待定条目写「带上 FlagGems X.Y.Z」。

> **注意：** 步骤 5（FlagGems 迭代测试）可能持续数周，期间步骤 6 会被反复执行。
> 每次 `configs.yaml` 更新 deps 或 FlagGems 修复后，都需要重新构建 runtime 镜像来验证。
> 步骤 8（生成 runtime 描述）只在最终验证通过后执行一次。

## 7. 验证 runtime 镜像（端到端）

在对应硬件的节点上手动验证：

```bash
docker pull harbor.baai.ac.cn/flagos-runtime/flagos-runtime-<vendor>-<backend>:<version>
docker run --gpus all harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:<version> \
  python -c "import flag_gems; ..."
```

如果验证失败：
- **包版本不兼容**：调整 `configs.yaml` → 返回步骤 4
- **FlagGems bug**：修补代码 → 重新打 tag → 返回步骤 5

## 8. 更新 runtime 描述

> **手动触发。**

```bash
gh workflow run gendoc-runtime.yml
```

生成 runtime 页面最终版本（含 `flag_gems` 版本号）。Review + merge PR。

> **注意：** 此步骤只在 runtime 镜像最终验证通过后执行一次。
> 描述内容来自 `configs.yaml`，runtime 镜像构建本身不触发此工作流。

## 9. 打 release tag

全部验证通过后：

```bash
git checkout main && git pull
git tag -f vX.Y.Z HEAD
git push -f origin vX.Y.Z
```

tag 含义：**这个 commit 上的整套 FlagOS 软件栈（base → runtime → FlagGems → runtime 重建）已经过验证。**

## 未决改进

- [ ] **泛化自动重试机制** — `gendoc-base.yml` 的 accumulate 已有自触发重试模式
  （restore state branch → 合并 artifact → `missing_versions.py` 查漏 → `gh workflow run`
  自触发，上限 50 次）。应泛化到所有多 backend 构建工作流
  （`base-image.yml`、`runtime-image.yml`、`flaggems-release.yml`），避免个别
  runner 因网络 / GitHub 连接波动失联导致整个 release 卡住。

  **需应对的失败场景**（环境原因，重试可能恢复）：GitHub / resource.flagos.net
  间歇性不可达；Harbor 连接暂时超时；runner 暂时离线。

  **不重试的场景**（重试无意义）：runner 磁盘不足（需手动清理）；代码 / 配置错误、
  SDK 安装失败、验证失败（需人介入修复）。
