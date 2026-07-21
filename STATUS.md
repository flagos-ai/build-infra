# Release Status

当前发布：**v2.1.1**。日期：2026-07-21。

## 当前步骤：2（构建 base images）

```
✅ 1. 更新 configs.yaml
🔄 2. 构建 base images
⬜ 3. 验证 + 生成描述
⬜ 4. 构建 runtime:v1
⬜ 5. FlagGems wheels
⬜ 6. 构建 runtime:v2
⬜ 7. 验证端到端
⬜ 8. 更新 runtime 描述
⬜ 9. 打 tag
```

## 步骤 2 状态

Run ID: 29846137289
触发命令：
```bash
gh workflow run "Base Image Build (manual)" -f backend="all" -f push="true"
```

| Backend | Runner | 状态 |
|---------|--------|------|
| nvidia-cuda13.3 | h20 | ✅ |
| nvidia-cuda12.8 | h20 | ✅ |
| metax-maca3.7.2.1 | metax | ✅ |
| mthreads-musa5.2.0 | musa520 | ✅ |
| ascend-cann8.5.0 | cann850 | 🔄 |
| ascend-cann9.0.0 | cann9 | 🔄 |
| cambricon-neuware4.4.3 | cambricon | 🔄 |
| kunlunxin-xre5.29.0 | kunlunxin | 🔄 |
| mthreads-musa4.3.6 | musa520 | 🔄 |
| enflame-tops1.9.10 | enflame | ❌ |
| hygon-dtk26.04 | hygon | ❌ |
| iluvatar-corex4.4.0 | iluvatar | ❌ |
| sunrise-tangrt1.2.0 | sunrise | ❌ |
| tsingmicro-tsm260604 | tsingmicro | ❌ |

### 卡点：磁盘检查 locale bug（5 个 backend 失败）

**根本原因**：`imagebuild.yml` 的 disk space check 用了 `df -BG | awk 'NR==2{print $4}'` — 在中文 locale 的 runner 上 `$4` 拿到了非数字列头（`Avail` vs `可用`）。enflame 失败原因待确认（run 未结束，日志暂不可查），可能同因。

**修复**：已 push 到 main（commit `0e0ce8a`），改用 `df --output=avail | tail -1`。

**后续操作**：
1. 当前正在跑的 job **不要动**，让它们继续
2. 已成功的 **不重复触发**
3. 等 run 结束后，只对 5 个失败的 backend **单独补跑**：

```bash
for b in enflame-tops1.9.10 hygon-dtk26.04 iluvatar-corex4.4.0 sunrise-tangrt1.2.0 tsingmicro-tsm260604; do
  gh workflow run "Base Image Build (manual)" -f backend="$b" -f push="true"
done
```

## 本次 release 周期的代码变更（v2.1.1 之后，已在 HEAD）

| Commit | 内容 |
|--------|------|
| `0e0ce8a` | fix(ci): locale-independent disk space check |
| `3a0111b` | feat(base): add vim to all 14 base images |
| `b62a97b` | fix: self-bootstrap git in cpp build script; revert target_backend |
| `5d9fc2c` | feat(base): add git to all 14 base images |
| `fdf7613` | fix: bash -c instead of file bind-mount for cpp wheel |
| `b9fec86` | fix: --entrypoint bash for docker run |
| `7b86869` | fix: full registry image ref for cpp wheel build |
| `6ea5dfd` | perf: uv from internal filestore instead of astral.sh |
| `c5cbeb3` | fix: yaml → pyyaml in runtime workflow |

## 已知待办

- [ ] 当前 base image build 跑完后，对 5 个失败的 backend 补跑
- [ ] 步骤 3 验证 base images + 生成描述 PR
- [ ] 步骤 4 runtime:v1（之前只构建了 nvidia-cuda13.3，本次需全部 14 backend）
- [ ] 步骤 5 cpp wheel 构建 — 4 轮调试已修了 ENTRYPOINT、文件挂载、镜像引用、git 自举等问题，实际 cpp 编译尚未跑通
- [ ] **泛化自动重试机制** — `base-descriptions.yml` 的 accumulate 已有自触发重试模式（restore state branch → 合并 artifact → `missing_versions.py` 查漏 → `gh workflow run` 自触发，上限 50 次）。应泛化到**所有多 backend 工作流**（`trigger.yml`、`runtime.yml`、`flaggems-release.yml`），避免个别 runner 因网络/GitHub 连接波动失联导致整个 release 卡住。

  **需应对的失败场景**：
  - 网络连接不稳定（无法访问 GitHub / resource.flagos.net）
  - Harbor 连接偶尔超时
  - runner 磁盘不足
  - runner 离线

  **不重试的场景**：代码/配置错误、SDK 安装失败、验证失败 — 这些需要人介入修复。
