# scripts/ — 脚本索引

入口文档。`packaging/` 下的代码改动（workflow 引用、verify 矩阵）都挂在这些脚本上，
先在此定位，再 grep 读最小片段。

## 索引

| 脚本 | 用途 | CI 引用 |
|---|---|---|
| `generate_matrix.py` | 从 configs.yaml 生成 CI matrix JSON（trigger/runtime/verify 等 workflow 的矩阵源） | ✅ |
| `build_base.py` | 构建 base 镜像（`--dry-run` / `--push`） | ✅ |
| `build_runtime.py` | 构建 runtime 镜像（解析 configs.yaml DEPS/编译器/FlagGems 版本 → build args） | — |
| `base_image_status.py` | 读已推送 base 镜像 revision/version OCI label，判定镜像是否过期 | — |
| `runtime_image_status.py` | runtime 镜像状态对比（`HARBOR_USER`/`HARBOR_PW` 环境变量） | — |
| `build_cpp_wheel.sh` | 在 runtime 镜像内构建 `flag-gems-cpp-<vendor>` wheel（env: `FLAGGEMS_REF`/`FLAGGEMS_CPP_VENDOR`/`FLAGGEMS_CMAKE_ARGS`/`SETUPTOOLS_SCM_PRETEND_VERSION`/`FLAGGEMS_BUILD_DEPS`） | — |
| `verify_base.py` | 从 build-config.yml 取 verify 命令，`docker run --rm <image> <verify-cmd>` | ✅ |
| `verify_runtime.py` | 拉镜像跑 runtime 内验证（flag_gems 简单 op） | ✅ |
| `verify-cpp-fixes.sh` / `verify-cpp-ops.py` | C++ wheel 修复验证 / C++ op 安装后验证 | ✅ |
| `verify_collect_cells.py` | verify-driver plan 任务：读 status matrix YAML，收集 ⬜ cell → matrix JSON | ✅ |
| `verify_dispatch_build.py` | verify-driver build 任务：读合并的 result JSON，对通过 cell 派发构建 | ✅ |
| `verify_record_results.py` | verify-driver record 任务：聚合逐 cell 结果，写符号、失败入 debug 队列 | ✅ |
| `verify_open_pr.py` | verify-driver record 任务：结果落定后开 PR | ✅ |
| `verify-nodes.example.yaml` | 验证节点映射样例（19 条，agent 用） | — |
| `verify-debug-loop` | 验证调试循环辅助脚本（verify-orchestrator.md §4.2 引用） | — |
| `annotate_version_tsv.py` | extract 任务：版本 TSV 打标注 → GitHub artifact | ✅ |
| `collect_version_tsvs.py` | accumulate 任务：git state 分支跨 retry 持久化版本 TSV | ✅ |
| `finalize_descriptions.py` | 描述文档定稿（review-gated PR 用，`--done` 两模式） | ✅ |
| `cpp_matrix.py` | C++ wheel 构建矩阵生成 | ✅ |
| `render_status_matrix.py` | 渲染 status matrix（源 = `packaging/<app>/status_matrix.<app>.yaml`） | ✅ |
| `record_app_image_tag.py` | app-image build workflow push 后自动记录 image tag | ✅ |
| `release_flaggems.py` | FlagGems release workflow（勿当测试用） | ✅ |
| `install-git-hooks.sh` | 安装 git hooks（status matrix pre-commit 用） | — |
| `version.py` | `image_version()` — 从 configs.yaml 取 flat tag | — |

## 约定

- `verify-*` 前缀 = verify 驱动（`docs/verify-orchestrator.md`）的组件；脚本间用
  JSON 文件交接（matrix → result），改动交接格式时同步改两端。
- 新增脚本：一句「用途 + 是否 CI 引用」补进上表；删除/改名脚本必须同步本表与
  `.github/workflows/` 引用。
