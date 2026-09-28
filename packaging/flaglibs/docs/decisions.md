# flaglibs wheel 发布 — 决策记录

## 范围

6 个 **纯 Python** FlagOS 算子库发布为可安装 wheel 到 **`flagos-pypi-hosted`**：
FlagAttention / FlagSparse / FlagBLAS / FlagAudio / FlagFFT / FlagGems-vllm。
FlagDNN（C++ runtime，无 Python 打包）与 FlagTensor（csrc 未接入 setuptools）
需上游先改造，本线不覆盖。

## 决策

### D1. hosted 而非 per-vendor 索引

纯 Python 包产出 `py3-none-any` wheel，与 vendor 无关。per-vendor 索引
（`flagos-pypi-{vendor}`）的边界是「vendor-bound binary」——绑定特定工具链的
wheel（flag_gems_cpp、torch_musa 等）才需要按 vendor 分索引。这 6 个库没有
设备二进制，单次发布到 released 仓库即可，全部 vendor 的 runtime 都能装。

Triton JIT 编译在运行时提供后端适配——wheel 层面无平台绑定。

### D2. tag 是版本

wheel 的版本是**构建 ref 的纯函数**：`default_ref` = 上游 release tag
（`v0.4.0` → `0.4.0`）。不引入 build-infra 侧的版本号——区别于 flagcx 的
`+<backend>` local label。这使「从 tag 构建」与「从 rc2 分支 head 构建」产出
**同一版本**（release tag = rc2 head，见下）。

### D3. release tag = rc2 分支 head

上游的 release 流程：rc2 分支 = 发布行（携带正确的 release 版本），release
tag 应等于 rc2 head。本线 6 个 tag 已对齐各自 rc2 head。构建从 tag 出发。

### D4. pyproject 静态版本 ≠ tag 是上游现状

构建时按 tag 出 wheel，不改版本号。`flagsparse`（0.3.0 vs v0.3.0 已对齐）、
`flag_blas` 等历史不一致已随版本归一修复；**若再有 tag 与 pyproject 不符，
以 tag 为准**，对齐属上游仓库的事。

### D5. flag_attn 用 setuptools_scm

`flag_attn` 的版本来自 git tag（scm 动态），构建需**全量 clone + `git fetch
--tags`**（浅 clone 不带 tag 则 scm 退化为 `0.0.0`）。其余 5 库 pyproject 静态
版本，浅 clone 足够。

### D6. 构建只在 CI

构建脚本可本地跑（dry-run 调试），但**发布动作只在 GitHub Actions**
（`flaglibs-wheel.yml`，manual dispatch）——本地构建的 wheel 不发布，与
flagtree/flaggems 同纪律。CI 用 `check-trigger-author` 守门。

### D7. 动态 `__version__`

上游 6 库的 `src/*/__init__.py` 已改为运行时从 installed metadata 读版本
（`importlib.metadata.version`），与 pyproject 单一事实源对齐（避免 pyproject
与硬编码字符串漂移）。此为**上游仓库的改动**（各 PR），本线只消费产物。

## 验证

1. CI 构建：6 个 `*-py3-none-any.whl`。
2. `unzip -l` 抽查包内容存在。
3. 发布后 `pip download --index-url https://resource.flagos.net/repository/flagos-pypi-hosted/simple <pkg>` 能拉到对应版本。

## 遗留

- FlagDNN / FlagTensor 待上游提供 Python 打包后扩展。
- 版本号对齐上游（如再有出入）——各上游仓库的事。
