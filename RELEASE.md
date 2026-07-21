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
- `flaggems` 此时留空。
- **此时不打 tag**。`version:` 只是声明"打算发布 `2.2.0`"；
  `scripts/version.py` 在 tag 不存在时返回纯版本号（不含 `-n`），
  构建不受影响。tag 在整个栈验证通过后才打。

提交并 push 到 main。

## 2. 构建 base images

GitHub Actions → **Base Image Build (manual)** → `backend: all`, `push: true`。

确认全部 backend 构建成功并推送到 Harbor。

## 3. 验证 base images + 生成描述

> 自愈合：触发一次 **Base image descriptions** 即可。extract 在 14 个硬件 runner
> 上 verify → dpkg-query → artifact，accumulate（ubuntu-latest）收集全部后自动
> 生成描述 PR。个别 runner 失联会自触发重试，全齐后开出 PR。

- [ ] 确认所有 backend verify 通过（PR 合并前检查 run log 即可）
- [ ] 系统包版本无意外大版本跳变（gcc、libc 等）
- [ ] 所有 backend 的描述均已生成

Merge PR。合并后 **base-descriptions-publish.yml** 和 **hugo-site.yaml** 自动
将描述推到 Harbor 和文档站。

## 4. 构建 runtime:v1（无 FlagGems，作构建平台）

Runtime 镜像的 venv（torch / flagtree / triton）是构建 FlagGems cpp wheel
的理想环境。先产出不含 FlagGems 的 runtime:v1 作为步骤 5 的构建平台。

每个 backend 在自己的硬件 runner 上构建，**仅本地保存**（不推 Harbor）：

```bash
python3 scripts/build_runtime.py nvidia-cuda12.8 --no-flaggems
```

14 个 backend 全部成功后进入步骤 5。

## 5. FlagGems 打 tag + 构建 wheels

- [ ] 在 FlagGems 仓库打 release tag（如 `v5.3.1`）

### 5a. Python wheel → 所有 vendor PyPI

GitHub Actions → **FlagGems Release Wheels** → `flaggems_ref=v5.3.1`：
- `python-wheel` job（ubuntu-latest）：`pip wheel` → 纯 Python `py3-none-any.whl`
- 推送到**所有 14 个** vendor PyPI

### 5b. Cpp operator wheel → vendor PyPI（cmake_backend 后端）

`cpp-wheels` job 矩阵，每个 vendor 在自己的 runner 上，docker run 本地 runtime:v1：

```bash
docker run --rm -v $PWD:/out runtime:v1 bash -c "
  git clone https://github.com/flagos-ai/FlagGems.git /tmp/src
  cd /tmp/src && git checkout v5.3.1
  tools/set_cpp_vendor.sh <vendor>
  pip install setuptools scikit-build-core pybind11 cmake ninja
  CMAKE_ARGS='-DFLAGGEMS_BUILD_C_EXTENSIONS=ON -DFLAGGEMS_BACKEND=CUDA ...' \
    SETUPTOOLS_SCM_PRETEND_VERSION=5.3.1 \
    pip wheel ./cpp --no-deps -w /out
"
```

构建完成后 readelf 检查 .so 的 DT_NEEDED / rpath，然后推送到对应 vendor 的 PyPI。

### 5c. 回填版本号

步骤 5a/5b 完成后，**更新 configs.yaml 中的 `flaggems` 字段**：

```yaml
flaggems: "5.3.1"
```

提交并 push。

## 6. 构建 runtime:v2（含 FlagGems，推送 Harbor）

runtime:v2 在 runtime:v1 基础上安装 flag_gems + cpp wheel（来自 PyPI），
推送到 Harbor 作为正式镜像。

GitHub Actions → **Runtime Image Build (manual)**（正常触发，不传 `--no-flaggems`）：
- `backend: all`
- `push: true`
- `flaggems` 留空（读取 configs.yaml 中的 `5.3.1`）

## 7. 验证 runtime v2（端到端）

构建并推送到 Harbor 后，在有对应硬件的节点上：

1. `docker pull` runtime image
2. 运行 `python tools/run_tests.py` 确认端到端可用

如果验证失败，根据错误类型回退：
- **包版本不兼容**：调整 `configs.yaml` → 返回**步骤 4**
- **FlagGems bug**：修补代码 → 重新打 tag → 返回**步骤 5**

## 8. 更新 runtime 描述

触发 **Base image descriptions** workflow (dispatch)，重新运行 `gen_data.py` +
`gen_descriptions.py`，生成 runtime 页面最终版本（含 `flag_gems` 版本号）。
打开 review-gated PR，审核后 merge。

## 9. 打 build-infra tag

全部验证通过后：

```bash
git checkout main && git pull
git tag -f v2.2.0 HEAD
git push -f origin v2.2.0
```

tag 的含义：**这个 commit 上的整套 FlagOS 软件栈（base images → runtime:v1 →
FlagGems → runtime:v2）已经过验证，可以发布。**
