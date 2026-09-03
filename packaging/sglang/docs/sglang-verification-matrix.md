# sglang 验证矩阵

> 规划工具，随验证推进更新。每单元格 = 对应后端 runtime 镜像 + `sglang 0.5.18+flagos`
> 单步安装 + `sglang-plugin-FL`（exp/0.5.18 分支 wheel）后，serve + 推理
> （Qwen3-0.6B）跑通的验证。
> 状态结论、根因与修复细节见 [sglang-0.5.18/index.md](sglang-0.5.18/index.md)、
> [sglang-0.5.18/playbook.md](sglang-0.5.18/playbook.md) 和
> [sglang-0.5.18/decisions.md](sglang-0.5.18/decisions.md)；本矩阵只记录状态。

## 状态图例

| 符号 | 含义 |
|---|---|
| ✅ | 已验证通过（serve + 推理 E2E） |
| ❌ | 已屏蔽 / 验证失败有结论（不交付，或需回退路径） |
| ⛔ | 挂起（需先解决上游阻塞） |
| ？ | 成功概率不确定（缺 vendor 变体依赖） |
| ⬜ | 待验证 |
| — | 该后端无此编译器 |

列名后缀：T = Triton 编译器，F = FlagTree 编译器。

PR 表"状态"列在渲染时经 `gh` 实时查询 PR 合并状态（已合并 / OPEN / 已关闭）；
查询失败显示 `—`，重新渲染即刷新。

## 矩阵

<!-- status-matrix:verification -->

| 厂商 | 后端 | 0.5.18(T) | 0.5.18(F) |
|---|---|---|---|
| 英伟达 | CUDA 12.8 | ⬜ | ⬜ |
| 英伟达 | CUDA 13.3 | ⬜ | ⬜ |
| 昇腾 | CANN 8.5.0 | ⬜ | ⬜ |
| 昇腾 | CANN 9.0.0 | ✅ | ✅ |
| 寒武纪 | NEUWARE 4.4.3 | ⬜ | ⬜ |
| 寒武纪 | NEUWARE 4.7.2 | ⬜ | ⬜ |
| 燧原 | TOPS 1.9.10 | ⬜ | ⬜ |
| 燧原 | TOPS 1.10.6 | ⬜ | ⬜ |
| 海光 | DTK 26.04 | ⬜ | ⬜ |
| 天数智芯 | COREX 4.4.0 | ⬜ | ⬜ |
| 天数智芯 | COREX 4.5.0 | ⬜ | ⬜ |
| 昆仑芯 | XRE 5.37.1 | ⬜ | ⬜ |
| 沐曦 | MACA 3.7.2.1 | ⬜ | ⬜ |
| 沐曦 | MACA 3.8.1.3 | ✅ | ✅ |
| 摩尔线程 | MUSA 4.3.6 | ⬜ | ⬜ |
| 摩尔线程 | MUSA 5.2.0 | ⬜ | ⬜ |
| 进迭时空 | SPACEMIT | ⬜ | — |
| 曦望 | TANGRT 1.2.0 | ⬜ | ⬜ |
| 平头哥 | PPU 2.0.0 | ⬜ | — |
| 清微智能 | TSM 260610 | ⬜ | ⬜ |

**后端级上游 PR（验证/镜像基于 PR 分支 Head 的跟踪项）**

| 厂商 | 后端 | App | PR | 状态 |
|---|---|---|---|---|
| 昇腾 | CANN 9.0.0 | sglang0.5.18 | https://github.com/flagos-ai/sglang-plugin-FL/pull/84 | OPEN |
| 沐曦 | MACA 3.8.1.3 | sglang0.5.18 | https://github.com/flagos-ai/sglang-plugin-FL/pull/86 | OPEN |

<!-- /status-matrix:verification -->

## 后端级上游 PR（验证/镜像基于 PR 分支 Head 的跟踪项）

<!-- status-matrix:facility:sglang0.5.18 -->

### sglang0.5.18

> 数据截止：2026-09-02

**App 级设施（全后端共享）**

| 事项 | 状态 |
|---|---|
| Containerfile | ✅ |
| 构建 workflow | ✅ |

**后端级设施**

| 后端 | deps_app 落库 | 启动文档 | 镜像发布 | 备注 |
|---|---|---|---|---|
| CUDA 12.8 | ✅ | ⬜ | ⬜ | — |
| CUDA 13.3 | ✅ | ⬜ | ⬜ | — |
| CANN 8.5.0 | ✅ | ⬜ | ⬜ | — |
| CANN 9.0.0 | ✅ | ✅ | ✅ | aarch64 cp311 双路径 E2E 全过（zero-sgl_kernel_npu shim + 插件层 torch-native stubs，exp/0.5.18/ascend）；坑见 backends/ascend.md |
| NEUWARE 4.4.3 | ✅ | ⬜ | ⬜ | — |
| NEUWARE 4.7.2 | ✅ | ⬜ | ⬜ | — |
| TOPS 1.9.10 | ✅ | ⬜ | ⬜ | — |
| TOPS 1.10.6 | ✅ | ⬜ | ⬜ | — |
| DTK 26.04 | ✅ | ⬜ | ⬜ | F 路径等待 flagtree hygon wheel 重建（FlagTree PR 已合，packaging/flagtree/hygon 待建） |
| COREX 4.4.0 | ✅ | ⬜ | ⬜ | — |
| COREX 4.5.0 | ✅ | ⬜ | ⬜ | — |
| XRE 5.37.1 | ✅ | ⬜ | ⬜ | — |
| MACA 3.7.2.1 | ✅ | ⬜ | ⬜ | — |
| MACA 3.8.1.3 | ✅ | ✅ | ✅ | — |
| MUSA 4.3.6 | ✅ | ⬜ | ⬜ | — |
| MUSA 5.2.0 | ✅ | ⬜ | ⬜ | — |
| SPACEMIT | ⬜ | ⬜ | ⬜ | 无基础镜像，排除 |
| TANGRT 1.2.0 | ✅ | ⬜ | ⬜ | — |
| PPU 2.0.0 | ⬜ | ⬜ | ⬜ | 无基础镜像，排除 |
| TSM 260610 | ✅ | ⬜ | ⬜ | — |


<!-- /status-matrix:facility:sglang0.5.18 -->
