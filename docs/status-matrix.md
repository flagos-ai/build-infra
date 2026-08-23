# Status Matrix（验证矩阵）结构化跟踪

> 验证矩阵的 markdown 表格适合人读、不适合机器同步；`status_matrix.<app>.yaml`
> 是表格的结构化副本（数据源），markdown 表格由 `scripts/render_status_matrix.py`
> 渲染生成。**改 YAML，不改 markdown 表格。**

## 文件布局

`status_matrix.*.yaml` 放在各 app 的 `packaging/<组件>/` 根目录下（不放
`docs/` 子目录）：

| 文件 | 组件 | app |
|---|---|---|
| `packaging/megatron/status_matrix.megatron_training.yaml` | megatron | megatron_training |
| `packaging/megatron/status_matrix.megatron_rl.yaml` | megatron | megatron_rl |
| `packaging/vllm/status_matrix.vllm0.20.2.yaml` | vllm | vllm0.20.2 |
| `packaging/vllm/status_matrix.vllm0.24.0.yaml` | vllm | vllm0.24.0 |

app 命名与镜像仓库的 app 段完全一致（app 与版本之间不加连字符）：
`vllm0.20.2` / `vllm0.24.0` / `megatron_training` / `megatron_rl`。
同一组件下多个 app 各占一个 YAML（0.20.2 与 0.24.0 视为两个 app）。

## 渲染目标与 marker 块

每个组件的 YAML 渲染进该组件的验证矩阵 md：

| 组件 | 渲染目标 |
|---|---|
| megatron | `packaging/megatron/docs/megatron-verification-matrix.md` |
| vllm | `packaging/vllm/docs/vllm-verification-matrix.md` |

渲染器只重写 md 内的 marker 块，块外内容（已知事实、阻塞、验证顺序等）
保持原样：

- `<!-- status-matrix:verification -->`：验证矩阵表格（该组件全部 app 合为
  一表）
- `<!-- status-matrix:facility:<app> -->`：单个 app 的设施清单

marker 块缺失时渲染器报错退出（防止手删块后静默丢失）。

## Schema

### 顶层

| key | 类型 | 说明 |
|---|---|---|
| `type` | string | `megatron` \| `vllm`，决定渲染目标 md |
| `app` | string | app key，须与 configs.yaml `deps_app` key 一致 |
| `description` | string | 人读说明 |
| `last_updated` | string | 数据截止日期（YYYY-MM-DD） |
| `facility` | map | app 级设施布尔（全后端共享） |
| `scenarios` | map | 场景 → 后端 → {T, F} 单元格 |
| `backends` | map | 后端级设施布尔 + 上游 PR 跟踪 |

### facility（app 级）

| key | 渲染列 |
|---|---|
| `containerfile` | Containerfile |
| `workflow` | 构建 workflow |

### scenarios

`scenarios.<sid>` 的 `label` 为矩阵列名；`verification` 每 key 为
`{vendor}-{backend}`（19 个，与 configs.yaml 后端一致），值为 {T, F} 两键
必填的单元格符号映射。

场景 sid（顺序固定）：megatron = `training` / `rl` / `post_training` /
`inference`；vllm = `inference`。

单元格符号图例（与 md 图例一致）：

| 符号 | 含义 |
|---|---|
| ✅ | 已验证通过（E2E） |
| ❌ | 已屏蔽 / 验证失败有结论 |
| ⛔ | 挂起（需先解决上游阻塞） |
| ？ | 成功概率不确定（缺 vendor 变体依赖） |
| ⬜ | 待验证 |
| — | 该后端无此编译器 |

列名后缀：T = Triton 编译器，F = FlagTree 编译器。

### backends

每 backend 必须含三个设施布尔（渲染为"设施落地"清单），`harbor_repo: true`
的后端同时必须带 `image_tag`：

| key | 渲染列 | 语义 |
|---|---|---|
| `deps_app` | deps_app 落库 | configs.yaml `deps_app` 该 app key 存在（key 存在 = 已验证，app 在该后端可构建） |
| `launch_docs` | 启动文档 | 启动文档是否落地 |
| `harbor_repo` | 镜像发布 | 该 app 镜像是否已推送 Harbor |
| `image_tag` | — | **必填当且仅当** `harbor_repo: true`：已推送的 Harbor 标签（如 `2.1.2-0.2.1_g825c1cd`）。由填 `harbor_repo` 的人同一处填写 —— 谁声明镜像已发布，谁负责同时记录 tag，二者是一次编辑里的一体事实。`docs/gen_data.py` 从这里的 `image_tag` 读已发布标签生成 app 镜像文档（不再维护独立登记表）；`vllm` app 的 `plugin_package` 也由此反推（tag 的 `-` 后段 `+`→`_`）。 |

`harbor_repo: false` 的后端**不要**写 `image_tag`（本地验证构建不等于已推送 Harbor）。

`prs`（可选，string 列表）：**上游** PR 跟踪项 —— 验证/镜像基于 PR 分支 Head
完成的那些 PR（如 vllm-plugin-FL / FlagTree / FlagGems 的 PR），合并后需联动
更新矩阵格与 fact 条目。设施落地 PR（build-infra 本仓库、由仓库内 PR 跟踪
体系负责）不放在这里，**facility 不携带 PR**。

## 刷新机制

1. **pre-commit hook**（`.githooks/pre-commit`，经 `scripts/install-git-hooks.sh`
   安装为 `core.hooksPath`）：暂存区含 status_matrix YAML 或 verification-matrix
   md 时运行 `render_status_matrix.py --check`；md 与 YAML 不一致 → 提交失败，
   提示先重跑渲染再提交。无关变更直接放行。
2. **CI 兜底**（`.github/workflows/status-matrix-consistency.yml`）：push 含
   status_matrix YAML（或手动 dispatch）时在 ubuntu runner 上重渲染并检测
   drift；有 drift 则以 flagos-ci 身份提交修复并开 review-gated PR
   （`auto/status-matrix-fix` 分支，dup-PR 检查复用 `finalize_descriptions.py`
   模式）。

## 使用

```bash
python3 scripts/render_status_matrix.py               # 渲染所有组件
python3 scripts/render_status_matrix.py --check       # 仅检查（hook / CI 用）
python3 scripts/render_status_matrix.py --component vllm
bash scripts/install-git-hooks.sh                     # 安装 git hooks
```

修改流程：改 YAML → 跑渲染器 → 提交两者。
