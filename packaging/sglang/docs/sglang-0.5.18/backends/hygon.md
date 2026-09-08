# sglang 0.5.18 — Hygon DTK26.04 验证记录

> **2026-09-08 验证通过（F/T 双路径）**。DTK 26.04 走 CUDA-alias 设备模型
> （`PlatformFL: vendor=hygon, device=cuda`），本轮阻塞集中在 sglang 0.5.18 对
> 注意力链路的 API drift；插件以 exp/0.5.18-hygon 分支三连 commit（头
> 440208b，正式 wheel `0.1.dev1+g440208beb`）对齐后 F/T 双路径 serve + 推理 E2E 全绿。

## 1. 环境

| 项 | 值 |
|---|---|
| 镜像 | `flagos-runtime-hygon-dtk26.04:2.1.2` |
| Python | 3.10.20 |
| torch | 2.9.0+das.opt1.dtk2604 |
| flagtree | 0.6.2a1+hcu3.6 @ `/opt/flagtree`（F 路径，内 triton 3.6.0）|
| vendor triton | 3.5.1+das.opt1.dtk2604.torch290 @ `/opt/triton`（T 路径）|
| flag_gems | 5.3.5（双路径共享）|
| sglang | 0.5.18+flagos |
| sgl-kernel-shim | 0.5.18 |
| sglang-plugin-FL | exp/0.5.18-hygon @ 440208b（wheel `0.1.dev1+g440208beb`）|
| 模型 | Qwen3-0.6B（`/public-flash/zyh-models/Qwen/Qwen3-0.6B`）|

## 2. 修复链（exp/0.5.18-hygon @ 440208b）

0.5.18 重构了注意力链路的配置与 KV-pool API，hygon 插件沿用老结构会读错对象。
serve 启动链暴露三个 drift，逐一以插件层 commit 修复（git log 溯源，同为
2026-09-08，wheel 落点 = 分支头 440208b）：

| 阻塞（sglang 0.5.18 drift） | 修复 commit |
|---|---|
| attention API 在 0.5.18 wheel 内移动了 import 路径 | d6f7acd0b：从 0.5.18 wheel 新路径 import |
| cuda_graph_config 改 per-phase，受控门禁原读取点失效 | 4949edd78：门禁改从 per-phase cuda_graph_config 读 |
| `ForwardBatch` 不再带 token_to_kv_pool（pool 移 ModelRunner）| 440208beb：KV pool 从 runner 读（根因，见 §4 #1）|

## 3. E2E 验证（F/T 双路径，正式 wheel）

判据：serve ready（log 出现 "The server is fired up and ready to roll" 且打印
"Using HCU attention backend"）后 3× chat/completions HTTP 200 +
completion_tokens>0 + sampling_backend=pytorch（经 /server_info 确认）。
模型 Qwen3-0.6B，max_tokens 144。serve 须按受控配置起（§4 #2）。

| 路径 | 编译器 | 结果 |
|---|---|---|
| F | flagtree 0.6.2a1+hcu3.6（triton 3.6.0）| ✅ 3/3 全过（ready ~100s，ct=144）|
| T | vendor triton 3.5.1（+das.opt1.dtk2604.torch290）| ✅ 3/3 全过（ready ~150s，ct=144）|

同一正式 wheel（0.1.dev1+g440208beb）上 T 先验、F 复验、T 再复验（冻结证据
log）均 3/3 全过。验证容器 `sglang-verify-hygon-dtk26.04` 保留。

app 镜像闭环：`sglang0.5.18-hygon-dtk26.04:2.1.2-0.1.dev1_g440208beb` 由
sglang-app-image workflow 在正式 wheel 上构建 + on-node verify（app 容器内
Step 7 serve E2E 3/3 全过）+ push（2026-09-08）；image_tag 由 record 步骤落库
（PR #794）。on-node verify 的 serve 受控参数由 #793 固化进
`verify-sglang-backend.sh`（hygon 分支自动带参，Step 7 无需再手动补）。

## 4. 坑清单

| # | 坑 | 处置 |
|---|---|---|
| 1 | 0.5.18 把 KV pool 从 `ForwardBatch` 移到 ModelRunner（树 backend 于 `__init__` 捕获），后端仍按老 API 从 ForwardBatch 读 | 插件 440208beb 改从 runner 读（§2）|
| 2 | serve 受控配置硬门禁：受控参数集不全，启动直接 RuntimeError | 起 serve 必须带下方受控参数集 |
| 3 | flag_gems SQL ConfigCache 跨编译器共享，F 调优配置被 T cache-hit 硬崩 | F/T 切换起 serve 前清 cache（命令见下）|
| 4 | 同容器 F/T 并行不可行（config_cache 互相清/投毒 + compiler env 进程级 + serve log 同路径）| 顺序跑，一次一个 compiler（本轮即顺序执行）|

受控 serve 参数（#2）：缺 `--disable-radix-cache` / `--disable-piecewise-cuda-graph`
任一 → 启动直接 RuntimeError "Strict HCU attention requires the controlled Qwen
server configuration"。完整参数集 = 下方命令中 `--model-path`/`--port` 以外的 flag：

```bash
python3 -m sglang.launch_server --model-path <模型路径> --port <端口> \
    --mem-fraction-static 0.6 --trust-remote-code \
    --page-size 64 --disable-cuda-graph \
    --disable-piecewise-cuda-graph --disable-radix-cache
```

flag_gems SQL ConfigCache 跨编译器共享（#3）：F/T 共用同 db
（`/root/.flaggems/config_cache/TunedConfig_*.db`），F 调优配置被 T cache-hit
复用 → 硬崩（PassManager::run failed）。切换 compiler 起 serve 前
`rm -f /root/.flaggems/config_cache/TunedConfig_*.db`（同 metax 线根因，见
[metax.md](metax.md)）。

## 5. 遗留

- 插件修复 PR #98（exp/0.5.18-hygon → exp/0.5.18）已开，与其他后端插件 PR
  （#84/#86/#90/#91/#92）对齐跟踪分支头（正式 wheel 由 sglang-plugin-wheel
  workflow 产出）。
- flagtree hygon wheel 由 flagtree 项目发布（版本已更新，runtime 内
  0.6.2a1+hcu3.6），非从 build-infra 重建；其上 0.5.18 F 路径实证全绿，本线无
  packaging/flagtree/hygon 重建待办（此前 status_matrix note 以该重建阻塞 F
  路径的判断不成立，note 已移除）。
