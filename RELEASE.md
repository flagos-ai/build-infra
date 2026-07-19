# FlagOS Release Workbook

## 前置检查

- [ ] `configs.yaml` 中所有 backend 的 `deps:` / `flagtree:` / `triton:` 版本已更新到目标版本
- [ ] FlagGems wheel（目标版本）已推到 `flagos-pypi-daily`
- [ ] 所有 base Containerfile 的 SDK 版本无需变更（本次 release 不涉及 SDK 升级则跳过）
- [ ] CI 上一次全量 base image build 已通过（无残留失败）

## 1. 更新 configs.yaml

修改 `version:` 和 `flaggems:`：

```yaml
version: "2.2.0"
flaggems: "5.4.0.dev601+g03122362d"
```

提交此变更到 main。

## 2. 打 tag

```bash
git checkout main && git pull
git tag -f v2.2.0 HEAD
git push -f origin v2.2.0
```

此时 `scripts/version.py` 对所有 backend 的 n 自动归零，tag 变为 `2.2.0`。

## 3. 构建 base images

在 GitHub Actions → **Base Image Build (manual)** → `backend: all`, `push: true`。

或本地逐 backend 构建：

```bash
for name in $(python scripts/generate_matrix.py | jq -r '.include[].name'); do
  python scripts/build_base.py "$name" --push
done
```

确认全部 14 个 backend 推送成功。

## 4. 生成描述（系统包版本）

方式 A：等待步骤 3 的 workflow 完成后，**base-descriptions.yml** 自动触发。

方式 B：手动触发 **Base image descriptions** workflow。

该 workflow 会：
- 从 Harbor 拉取每个已构建的 base image
- 运行 `dpkg-query` 提取系统包版本
- 运行 `gen_data.py` + `gen_descriptions.py` 生成全量描述
- **打开一个 review-gated PR**

## 5. 审核描述 PR

- [ ] 检查 PR diff 中的版本号是否正确
- [ ] 检查系统包版本是否有意外的大版本跳变（gcc、libc 等）
- [ ] 确认所有 backend 的描述均已生成

审核通过后 merge PR。合并后 **base-descriptions-publish.yml** 自动将描述推到 Harbor。

## 6. 构建 runtime images

在 GitHub Actions → **Runtime Image Build (manual)**：

- `backend: all`
- `push: true`
- `flaggems: 5.4.0.dev601+g03122362d`（与 `configs.yaml` 一致）

或本地：

```bash
for name in $(python scripts/generate_matrix.py | jq -r '.include[].name'); do
  python scripts/build_runtime.py "$name" --push
done
```

## 7. 更新文档站

合并到 main 后（含生成的 `docs/content/`），**hugo-site.yaml** 自动触发，将文档站部署到 `flagos-ai.github.io/release-info`。

确认文档站可访问，各 backend 页面版本号正确。

## 8. 验证

- [ ] `docker pull harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda12.8:2.2.0` 可拉取
- [ ] `docker pull harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:latest` 可拉取
- [ ] 选 1-2 个有硬件的 backend（如 nvidia on h20）跑 `docker run` + verify 命令
- [ ] 文档站各 backend 页面可访问
- [ ] Harbor 上各 base image 的 repository description 已更新
