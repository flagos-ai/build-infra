# docs/vendors/ — 厂商平台事实层

一个厂商一页（`docs/vendors/<vendor>.md`，键 = `configs.yaml` 的 vendor）。本目录
回答的问题是：**换 app、换 app 版本都仍然成立的那条平台事实，写在哪。**

## 收什么、不收什么

收（变化轴 = 厂商）：

- 设备枚举命令与设备节点名；一个 index 代表什么（卡 / die / 芯片）。
- 容器 runtime / toolkit 的行为与**不做**的事，以及启动方式错了会看到什么。
- 容器内环境发布机制：哪些 shell 看得到厂商 env，看不到时的失败长什么样。
- 设备状态危险：什么会把设备占住 / 卡死，怎么发现，假失败长什么样，恢复代价。
- 供应商工具链：torch fork 自报的 `device.type`、是否自带 triton、cmake backend。
- 平台级 kernel / op 地雷，与硬件能力边界（dtype、指令集、die 数量）。

不收（变化轴不是厂商，去别处）：

| 这条事实会随什么变化 | 去哪 |
|---|---|
| app 版本（本版 repack 配方、阻塞点、遗留项、验证结论） | `packaging/<app>/docs/<app>-<ver>/backends/<vendor>.md` |
| 单元格通过状态 | `status_matrix*.yaml`（渲染器生成表格） |
| 启动 flags 的**原文** | `.github/build-config.yml` `run.vendors.<vendor>` —— 厂商页只写「这条 flag 为什么必须这样」，不复制 flag 文本 |
| runner 标签 / 主机名 | `.github/build-config.yml` `runners.overrides`、`scripts/verify-nodes.example.yaml` |
| 是哪台物理机、谁在上面验证 | `scripts/verify-nodes.local.yaml`（git-ignored）——**厂商页不写主机名、不写用户名、不写路径** |

## 硬规则

1. **不做 flag 的第二份副本。** 厂商页引用 `.github/build-config.yml`，不复述其
   内容。复述一次就会分叉一次。
2. **上限约 80 行。** 超了说明混进了 app 版本内容，把它挪回该版本的 backend 记录。
   （ascend / kunlunxin / cambricon 已在上限附近，它们线最多、坑也最多。）
3. **只记结论与后果。** 不写探索过程、不写"试了三次"。现象 + 根因 + 后果三行内
   说完，细节指向已有记录。
4. **该厂商独有的教训才写。** 所有厂商都一样的（例如"先清理残留容器"）属于
   `node-ops` 技能，不属于任何厂商页。
5. **过时的事实删掉，不保留。** 记录里被证伪过的说法（例如"容器内没有 npu-smi"）
   不要搬进来；搬更正后的结论。

## 模板

小节名不强制统一，但下列内容各归一处（用哪几个小节由该厂商有什么决定）：

```markdown
# <vendor>（<中文名>）

<一行：是哪家的什么芯片 / 哪些 backend key 属于它>

## 平台与设备

- <设备枚举命令>；<device 节点名>；<一个 index = 卡还是 die>
- <架构 / python 版本 / 芯片代际之间的结论不可互相套用>

## 启动容器

- <这条 launch flag 为什么必须这样（后果），flags 原文见 build-config.yml>

## 容器内环境

- <哪些 shell 看得到厂商 env；看不到时的失败签名>
- <构建期注意：什么必须在 bash 里 source、什么必须在什么之后>

## 设备状态危险

- <什么会占住设备；假失败长什么样；恢复代价>

## 供应商工具链

- <device.type 自报值 / 是否自带 triton / cmake backend / 已知不可修复缺陷>
- <设备能力自报值（capability、shared memory、grid 上限）—— 按它分支的逻辑会被它骗>

## 平台级 kernel / op 地雷

- <哪个算子在本地硅上静默算错；哪个 env guard 在 serve 路径上不生效>

## 指针

- 逐后端记录：`packaging/<app>/docs/<app>-<ver>/backends/<vendor>.md`
- <其他权威源>
```

没有内容的小节**不要留空标题**（spacemit / thead 就只有一个「现状」段）。

## 谁写、什么时候写

厂商页**不是**一次性生成后冻结的：它随每条 app 线的验证顺手沉淀——某条厂商事实
第一次被第二个 app 复用时，就该从 backend 记录搬到这里。搬运时留指针，不留副本。
