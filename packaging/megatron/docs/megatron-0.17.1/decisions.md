# Megatron 0.17.1 决策记录

## 自动化边界

- **矩阵 cell 驱动**：验证状态由 `packaging/megatron/status_matrix.<appkey>.yaml`
  驱动（`scripts/render_status_matrix.py` 渲染成
  `docs/megatron-verification-matrix.md`）；cell 只记状态，细节在
  `backends/<vendor>.md`。
- **verify 门禁 push**：app 镜像 workflow 内 verify（`--app-image` 模式：
  BEFORE = runtime / AFTER = app 包矩阵 unchanged + megatron.core import +
  helpers_cpp 绑定）通过才推送 Harbor。
- **record_app_image_tag**：镜像发布 tag 自动记录（`record_app_image_tag.py`），
  image_tag 为已发布 tag 唯一事实源。
- **`--scenario rl` 不自动化**：上游阻塞（[MLF #116](https://github.com/flagos-ai/Megatron-LM-FL/pull/116) + flash-attn 依赖），RL
  cell 标 ⛔ 不收集。
- **断言不进最终镜像**：锁版才是交付契约；verify 断言是测试阶段手段。

## ADR

### ADR 1: fork 源码 wheel vs repack

megatron 是 fork 源码模式：wheel 从 Megatron-LM-FL 构建，保留
`torch>=2.6.0` Requires-Dist（runtime vendor torch 满足，pip 解析零下载），
**不 repack、不做 METADATA 手术**。对比 vllm 的 repack 模式（sdist 的 deps
会拉公共 PyPI torch 覆盖 vendor 构建，必须剥依赖）。repack facility 已删除
（2026-08-14）。

### ADR 2: helpers_cpp 按 cp-version 全量上传

wheel 含 pybind11 编译扩展，CPython-ABI 特定——cp310 / cp311 / cp312 三
版本全量构建上传（runtime 矩阵三种 Python 都在用，任一缺则对应后端装不上）。
`optional=True` 会静默跳过编译失败，Containerfile 以 `.so`-in-wheel gate
兜底。

### ADR 3: megatron 不 --no-deps vs verl 必须 --no-deps

megatron 单步安装**不 `--no-deps`**：wheel 声明（`torch>=2.6.0` 等）与
runtime 满足关系闭合，pip 判定已满足、零下载覆盖。verl **必须
`--no-deps`**：verl 自身 `numpy<2.0.0` 与 runtime `numpy==2.3.5` 冲突，
依赖须显式钉版本（`--no-deps` 需闭包验证）。

### ADR 4: wheel 版本格式 `0.17.1+fl.<date>.g<sha>`

本地段 = fork commit 溯源（日期 + 精确 commit），构建可复现、可审计。PEP
440 忽略 local label，`==0.17.1` 匹配不受影响，既有 pin 保持解析。

## 风险痛点

- **cambricon kernel 重写**：runtime 5.3.3 之后 +39k kernel rewrite，旧 E2E
  结果不背书新产物——发布前需复验（见 [backends/cambricon.md](backends/cambricon.md)）。
- **merged wheel 参数接口重构**：config dataclass 化后 `--lr` /
  `--eval-interval` 等默认 None，喂参接口变更——所有用 merged wheel 的后端
  需逐参数重核参数基线。
- **跨后端 wheel 共享未验证**（决策 6）：cp310 wheel 是否可在全部 py3.10
  后端共享，待全部验证通过才下结论；py3.11 / py3.12 同样各过一遍。
- **modelopt 版本约束**：`nvidia-modelopt` 的 torch 约束随版本演进（0.45.0
  时代曾解析出 torch 2.13 替换 vendor torch），抬版本前先核 torch 约束。
- **flash-attn 依赖面**：动态引擎硬依赖 flash-attn（`attention.py` 内核
  断言）；非 CUDA 平台 vendor 包路线关闭时 RL 全链暂停（ascend 950 之前
  型号）。
