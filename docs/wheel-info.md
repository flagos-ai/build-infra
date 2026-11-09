# Wheel Info（wheel 包目录的自动记录机制）

> `packaging/packages.yaml` 是全部 wheel 的包目录，并同时给出每个包的源码包
> 下载信息。本文件说明这两部分如何维护：wheel 的事实由发布步骤记录，源码包
> 信息由人工维护，人工只 review 由记录产生的 PR。本文件只描述机制与设计理由；
> 具体实现见 `scripts/gen_wheel_info.py`、
> `.github/actions/record-wheel-info/action.yml` 与
> `.github/workflows/record-wheel-info.yml`。

## 问题

目录中每条事实（`pypi_index` / `python` / `os` / `arch`）都产生于某一次发布，
但过去由人在发布 PR 中手工修改，因此目录与各 PyPI index 上实际存在的包持续
不一致（#1325–#1327 即为手工修改字段的 PR）。判定「某个 wheel 已经发布」的
唯一确切位置是发布步骤本身，因此记录动作放在发布步骤中。

## 数据模型

目录文件本身就是记录，不另设数据文件。`packaging/packages.yaml` 有两个顶层键：

- `wheels:` —— wheel 的下载信息。每个包一条；包内**每个具体 wheel 一条记录**
  （同一版本出现在多个平台时为多条）。
- `sources:` —— 同一批包的源码包下载信息。每个包一条，与 `wheels:` 的包名一一
  对应，顺序一致。

### `wheels:`

| 内容 | 维护者 | 说明 |
|---|---|---|
| `name`、`versions[].version`（含排列顺序） | 人工 | 包与版本的排列顺序由人工决定 |
| `short_name`、`desc_zh`、`desc_en`、`notes`、`notes_en` | 人工 | 目录页面文案，记录过程不修改 |
| `pypi_index`、`python`、`os`、`arch` | 程序 | 由发布事件推导，`record` 仅修改这四个字段 |

**一条记录对应一个具体的 wheel**：`(version, python, os, arch)` 四元组唯一
确定它。同一版本在不同平台上依赖的产品不同（例如 `vllm` 的 wheel 本身是
`py3-none-any`，但每个平台依赖的 `xgrammar` 等闭包不同），所以平台也属于
记录身份的一部分，而不是记录内部的一个取值。

因此 `python`、`os`、`arch` 是**标量**，只有 `pypi_index` 可以是列表——同一份
字节被发布到多个 index。把多个平台值塞进一条记录（或让生成器对多个列表取
笛卡尔积）会描述出实际不存在的产物，例如「所有 index 上都有 aarch64 wheel」。

`record` 的修改范围限于匹配 `(name, version, python, os, arch)` 的那条记录的
四个字段，属于局部更新。若目录中不存在该包或该 wheel，则插入一条骨架记录
（`short_name` 取包名，文案字段留空），并在 PR 中输出提示：该骨架记录表示文案
仍需人工补写。

### `sources:`

每个包一条，与 `wheels:` 的包名一一对应、顺序一致（两边对齐由人工维持，
没有程序检查）。字段全部由人工维护：

| 字段 | 说明 |
|---|---|
| `name`、`short_name` | 与 `wheels:` 中同名包的取值一致 |
| `desc_zh`、`desc_en` | 包级一句话：这个包是什么。站点上源码条目的描述文字 |
| `url` | 下载地址模板，唯一占位符 `{version}` |
| `versions[].version` | 源码版本，见下 |
| `notes`、`notes_en` | 可选，面向下载者的一句话，只写与同包 wheel 的差异；`notes` 为中文、`notes_en` 为英文 |

`sources:` 的记录粒度是「仓库」：它不随发布变化，也没有任何发布步骤能观察到它。
因此 `record` 不写这一半——包括新包首次发布时——它在 `wheels:` 插入骨架行，
`sources:` 仍由人工补写。

#### 源码版本独立于 wheel 版本

两边只有**包名**对应，版本各是各的，不能从 wheel 版本推源码版本：同一份源码
可以产出一批平台构建变体，也可以一个 wheel 版本对应一份源码。

| 包 | wheel 版本 | 源码版本 | 为何不同 |
|---|---|---|---|
| `flagcx` | 20 | 1（`0.14.0`） | `+<backend>` 是构建平台，不是源码版本 |
| `torch-fl` | 7 | 1（`2.10.0`） | 同上 |
| `megatron-core` | 2（`0.17.1+0.2.3`） | 2（`0.2.3`、`0.3.0`） | 源码 tag 是 fork 分支号，与 wheel 的 `0.17.1` 无关 |
| `flagtree` | 14 | 14 | 上游 tag 自带后端段（`0.7.0+metax3.6`），每个后端一份源码 |

全部 14 个包合计 55 个 wheel 版本、30 个源码版本。

`desc_zh` / `desc_en` 写在**包**一级，而不是逐版本写：`wheels:` 的 desc 按
平台版本写（「面向昇腾 CANN 9.0.0 的……」），源码条目没有平台维度可挑，
逐版本写只会重复同一句话。

#### 下载地址

`url` 是**完整下载地址**的模板，把该条目 `versions[]` 里的版本填入 `{version}`
即得一个可直接下载的 `.tar.gz` 地址。例如 `vllm` 的模板是
`https://github.com/vllm-project/vllm/archive/refs/tags/v{version}.tar.gz`，
版本 `0.24.0` 即得
`https://github.com/vllm-project/vllm/archive/refs/tags/v0.24.0.tar.gz`。

**不做版本推导。** 早期设计让模板从 wheel 版本取数、用 `{version_base}` /
`{version_local}` 切分 `+` 前后，这要求每个 wheel 版本都恰好对应一个源码 tag，
而上面四行里有两行不成立（`+<backend>` 是平台，`0.17.1` 是无源码含义的段）。
模板只认自己那条目里的版本，就再不需要任何启发式。

同理，`notes` 不写模板机制（「tag 只到 vX」「无 `v` 前缀」）——那是本文件的
内容，下载者看不到也不关心。它只写源码与同包 wheel 的差异：`vllm` 的 wheel
是 repack 的、`megatron-core` 取自 fork、`flagcx` 的多平台 wheel 共用这一份源码。

渲染地址时把 tag 部分做百分号编码（`+` 写作 `%2B`）再请求：`flagtree` 的源码
版本自带 `+`，而带字面量 `+` 的地址时好时坏。

其余约定：

- **记录事件，不做重新校验。** 一条记录的内容是产生它的若干次发布的并集（平台
  四元组已确定，事件之间只会增加 `pypi_index` 通道）；某个事件已记录时，比对
  结果无差异，因此不产生提交、不产生 PR。幂等性通过比对记录内容判断，不维护
  事件日志。
- **平台是记录身份，不是记录取值。** `python` / `os` / `arch` 由事件给出，
  一条记录一个标量组合；同一版本在第二个平台发布时新增一条记录，而不是把
  平台值追加进已有记录——拼接出来的组合（`cp312` 配 `aarch64`、`any` 配
  `linux_x86_64`）描述的是不存在的产物。
- **`pypi_index` 唯一可多值。** 只有一个发布通道时为字符串，多个通道时为列表且
  `flagos-pypi-hosted` 排首位。其它三个机器字段恒定单值。
- **manifest 中的 `pkg` 是目录中的包名，不是 wheel 文件名。** 文件名不足以
  推出包名（`vllm_plugin_fl` 对应目录名 `vllm-plugin-fl`，`sglang_fl` 对应
  `sglang-fl`），因此包名由各发布步骤显式给出。

## 处理流程

```
发布步骤（twine 返回成功后）
  ├─ 在主机侧追加一行到 .wheel-info/manifest.tsv（该路径已被 .gitignore 忽略）
  │     每行四列（制表符分隔）：pkg、version、index、filename
  │     version 留空表示由 wheel 文件名推导
  └─ 作为 artifact 上传，artifact 名以 wheel-info-manifest- 开头
        │
        ▼
记录作业（每次 workflow run 仅一个）
  ├─ 下载 artifact（pattern: wheel-info-manifest-*，不使用 merge-multiple）
  ├─ 合并为一份 manifest
  └─ 调用 ./.github/actions/record-wheel-info
       └─ scripts/gen_wheel_info.py record --manifest … --workflow …
            └─ 修改 packaging/packages.yaml → 提交 → 创建待 review 的 PR
```

以下两点改动时容易出错：

- **每次 run 只有一个提交者。** 发布步骤不修改 `packages.yaml`。矩阵扇出
  （`backend: all`）会产生多个并行作业同时发布，若各自提交并创建 PR 会互相
  冲突；因此合并放在唯一的记录作业中，无论扇出多少路都只有一个提交者。
- **下载 artifact 不能使用 `merge-multiple`。** 各作业上传的 artifact 内部
  文件名相同（均为 `manifest.tsv`），展开到同一目录会互相覆盖，只剩一份。
  因此保持「一个 artifact 一个目录」。注意 pattern 只命中一个 artifact 时
  `download-artifact` 会把文件直接摊进下载路径、不建子目录，所以收集按路径
  递归查找 `*.tsv`，不能写死目录层级。

## 作业形态

记录作业的作业体在所有 wheel workflow 中内容相同，已抽为可复用工作流
`.github/workflows/record-wheel-info.yml`（触发方式为 `on: workflow_call`）。
调用点只保留各 workflow 互不相同的三项内容：

```yaml
  record-wheel-info:
    needs: build
    if: ${{ always() && inputs.upload && !cancelled() }}
    permissions:
      contents: write
      pull-requests: write
    uses: ./.github/workflows/record-wheel-info.yml
    with:
      workflow: vllm        # 对应分支 auto/wheel-info-vllm，也是 PR 中的来源名称
```

- **调用作业不能出现 `runs-on` 与 `steps`。** 调用可复用工作流的作业仅允许
  使用 `name`、`uses`、`with`、`secrets`、`strategy`、`needs`、`if`、
  `concurrency`、`permissions`、`cache-mode` 这些键，因此作业体（checkout、
  下载 artifact、合并、调用 composite action）全部位于被调用工作流中。
  composite action `.github/actions/record-wheel-info/` 位于更内一层，负责
  选择一个能 `import yaml` 的解释器（无法导入时尝试安装，安装失败则以错误
  退出并给出提示）。
- **`permissions` 必须保留在调用点。** 它是记录作业获得仓库写权限与创建 PR
  权限的来源；被调用工作流只能降权，不能提权（未在调用作业指定
  `permissions` 时，被调用工作流将使用 `GITHUB_TOKEN` 的默认权限）。
- **`if` 中的 `always()` 是必要的。** 发布步骤中途失败时留下的 manifest 仍然
  记录了「哪些包确实已上传」；同时 `always()` 可避免被跳过（skipped）的
  `needs` 作业被误判为成功。真正的准入条件是后半段的发布开关
  （`inputs.upload` 或 `inputs.publish`）。
- **`workflow:` 必须作为输入传入，不能从上下文读取。** 被调用工作流中的
  `${{ github.workflow }}` 是调用方的名称，因此每个调用点显式传入自己的名称。

## 已接入与未接入

已接入，共 11 个 workflow：`flagcx-wheel`、`flaggems-release`（python 与 cpp
两条构建线）、`te-fl-release`、`flash-attn-wheel`、`flaglibs-wheel`、`vllm-wheel`、
`vllm-plugin-wheel`、`sglang-wheel`（build 与 shim 两个作业）、
`sglang-plugin-wheel`、`megatron-wheel`、`flagos-compressor-wheel`。

未接入，且属于有意为之：

- `flaggems-wheel`、`flaggems-vllm-wheel`、`flagtree-wheel`、`flagtree-wheel-daily`、
  `flagtree-builder` 五个 workflow 明确不接入。前四个的版本号带日期
  （如 `0.7.1.dev<date>`），与上面 megatron 的情形同构；`flagtree-builder` 只发布
  构建镜像，不出 wheel。
- `megatron-wheel` 的 provenance 构建（版本号形如 `0.17.1+fl.<date>.g<sha>`）
  不记录：该版本号不对应任何发布版本，只有传入 `mlf_version` 的正式发布才记录。
- `sources:` 不记录（原因见「数据模型」一节）；`sglang`、`sgl-kernel-shim` 等
  已有发布步骤但 `wheels:` 中尚无条目的包，其 `sources:` 条目也待人工补写。
- `torch-fl` 的 7 行没有对应的发布流水线，继续由人工维护。
- deb/rpm 各线、app 镜像各线、gendoc 各线均不属于本机制范围。

## 已知边界

- 目录文件经 YAML dumper 写回，因此**文件布局**（键的顺序、列表缩进）由
  dumper 决定：写在目录文件**内部**的注释无法在一次记录后保留，作为字段**值**
  写入的文案可以保留。当前文件可以通过 dumper 逐字节往返，这是需要维持的
  性质。
- 没有 CI 一致性检查（原设计中的 `render --check` 未实现）。记录由发布触发，
  不是定时校验。

## 验证

- `record --dry-run` 输出 unified diff 且不写盘：写入前不修改任何文件。
- 已人工核对的行为：重复记录同一事件不产生改动；实际合并产生单个由 `flagos-ci`
  提交的提交，分支名为 `auto/wheel-info-<workflow>`；手写 `desc_zh` 逐字节
  不变，仅目标字段发生变化；新平台的事件新增一条记录而非改写已有记录。
- 10 个 workflow 的 manifest 步骤已分别抽取、渲染其环境变量并在临时目录中
  执行：15 个用例（含 megatron provenance 应记录 0 行、flaggems-release 扇出
  14 个发布通道）全部通过；每行均为 4 个制表符分隔字段，`record --dry-run`
  接受其合并结果。
- `sources:` 的 30 个源码地址（14 个模板，各自填入 `versions[]` 中的版本）
  已逐一对上游仓库的 tag 列表求交，并实际请求：30/30 命中且返回 200。
