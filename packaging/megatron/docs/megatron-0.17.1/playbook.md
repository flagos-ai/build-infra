# Megatron 0.17.1 playbook

## 标准流程

### ① wheel 构建（`packaging/megatron/builder/` + `megatron-wheel.yml`）

- 构建环境 = 后端 runtime 镜像本身（无独立 toolchain 镜像），每后端一个
  wheel；构建环境 == 交付环境，装完即可做依赖面安全验证。
- 版本号自动带 commit 溯源：`0.17.1+fl.<date>.g<sha>`（`MLF_VERSION` 可
  覆盖）。
- 两个门禁：`.so`-in-wheel gate（helpers_cpp 编译失败会被 `optional=True`
  静默跳过，zipfile 扫描兜底）+ smoke test（完整 pip install 后 importlib
  加载 helpers_cpp 绑定）。
- 三 cp 版本（cp310 / cp311 / cp312）全量上传 flagos-pypi。
- **重建陷阱**：打包 commit 可能只存在于 MLF 分支持（如 ba22f6b673f3 在
  feat/wheel-full-scope），构建前先确认 `MLF_REF` 指向的目标。

### ② app 镜像（`megatron-app-image.yml`）

- 从 `flagos-runtime-{vendor}-{backend}` 构建
  `flagos-app/{app}{app_version}-{vendor}-{backend}:{tag}`（`{app}` =
  `megatron_training` | `megatron_rl`，app 名与版本号之间不加连字符）。
- 单步安装 `megatron-core[{extra}]`（**不 `--no-deps`**）；`[training]` /
  `[rl]` extra 选择 + vendor 条件包（configs.yaml `deps_app`，仅 hygon rl
  有 TE）。
- workflow 内 verify（`--app-image` 模式）通过才 push。

### ③ 节点 verify（`packaging/megatron/verify/verify-megatron-backend.sh`）

```
./verify-megatron-backend.sh <vendor-backend> \
    [--app-image <tag>] [--compiler flagtree|triton] [--scenario training|rl]
```

- 步骤：起容器 → BEFORE 依赖快照 → 单步安装（或 `--app-image` 跳过，安装
  已在镜像构建期发生）→ AFTER 快照对比（torch / triton / flag_gems /
  numpy 逐位不变）→ megatron.core import + helpers_cpp 绑定 → mock-data
  pretrain_gpt 5 iter exit 0。
- **F/T 双路径都必须跑**（验证面不归并）：`--compiler flagtree` 与
  `--compiler triton` 各一遍，loss 逐位一致才算过。
- `--scenario rl` 被脚本拒绝（上游阻塞：MLF #116 + flash-attn），RL cell
  标 ⛔ 不收集。
- 陈旧 checkout 时用 `--stack-version` 显式钉 runtime 镜像 tag（repo root
  固定路径，无 walk-up）。

## 弯路记录

| 弯路 | 现象 | 处置 |
|---|---|---|
| flash_attn 版本断言 | `flash_attn.__version__` 硬编码 "2.6.1" 检查，vendor 变体不适用 | 随 MLF #116 按 DotProductAttention 跳过 |
| TORCHINDUCTOR_COMPILE_THREADS | flagtree inductor fork × driver current_device 崩溃 | 镜像 ENV 固化 =1（进程内编译） |
| apex | MLF 4 处使用全 try/except fallback | 熔断可选；hygon runtime 纳入 vendor apex |
| tensorboard 未声明依赖 | rl_utils.py:24 import 期阻塞 → has_rl_utils=False 断言 | 补装；MLF 反馈项 |
| cambricon `_copy_from` kernel 缺失 | NPU 递归分发 segfault（torch_npu 缺 PrivateUse1 kernel） | FlagGems #4962/#4960 闭环 |
| `--lr` / `--eval-interval` 默认 None | merged wheel 参数接口重构，不传即 TypeError | 复现基线强制传参 |
| `--no-persist-layer-norm` 缺失 | post_training 撞 torch_norm.py:48 断言（persist 默认 True） | 必传参数 |
| torch-first 导入顺序（ascend） | `import triton` 先于 torch 即崩（flagtree backend discovery） | FlagTree #1025 惰性化前保持 torch-first |
