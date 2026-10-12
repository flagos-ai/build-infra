# Wheel Info（wheel 目录自动记录）

> `packaging/wheel-info.yaml` 是 wheel 包目录。本文件说明它如何被自动维护：
> 发布即记录，人只 review PR。**为什么这么设计**在这里，**怎么做**在代码里。

## 问题

目录里每一条事实（`pypi_index` / `python` / `os` / `arch`）都来自某一次发布，
但过去靠人在发布 PR 里手改，于是目录与实际 index 上有的包持续漂移
（#1325–#1327 就是手改字段的 PR）。唯一确定「某个 wheel 已经存在」的地方是
**发布步骤本身**，所以记录点就在发布步骤。

## 数据模型：目录即记录

不存在第二个数据文件。`packaging/wheel-info.yaml` 一个文件承担两半：

| 字段 | 谁写 | 说明 |
|---|---|---|
| `name` / `versions[].version` | 人（顺序也是） | 包与版本的排列顺序是人定的 |
| `short_name` / `desc_zh` / `desc_en` / `notes` | 人 | 目录页文案，机器不碰 |
| `pypi_index` / `python` / `os` / `arch` | **机器** | 由发布事件推导，`record` 只改这四个 |

因此 `record` 是**外科式**的：只更新匹配 `(name, version)` 行的这四个字段。
遇到目录里没有的包/版本，它会插入一行骨架（`short_name` = 包名，文案留空）并在
PR 里打印提示——骨架行就是给 reviewer 的「这段文案还没写」信号。

其余约定：

- **事件，不是重新校验**。一行是若干次发布的并集；事件已记录 ⇒ 无改动 ⇒
  不产生 commit、不产生 PR。幂等性由「比对行本身」回答，没有事件日志。
- **`py3` 事件替换而非合并**：一个 `py3-none-any` 事件把该行的 python/os/arch
  整体替换为 `[py3]/[any]/[any]`；编译型事件落在 `py3` 行上同样替换。理由是
  `cp312` 旁边并存的纯 wheel、`linux_x86_64` 旁边的 `any`，描述的是不可能存在的包。
- **排序固定**：python `cp310→cp313, py3`；arch `linux_x86_64, linux_aarch64, any`。
  `pypi_index` 单 lane 是字符串，多 lane 是列表且 `flagos-pypi-hosted` 排第一。
- **manifest 的 `pkg` 是目录名，不是 wheel 文件名**。文件名不可信
  （`vllm_plugin_fl` → 目录名 `vllm-plugin-fl`，`sglang_fl` → `sglang-fl`），
  所以包名由 hook 显式给出。

## 管线

```
publish step（twine 成功后）
  └─ 主机侧追加一行 → .wheel-info/manifest.tsv   (git-ignored)
       列：pkg \t version \t index \t filename   （version 留空 = 从文件名推导）
  └─ 作为 artifact wheel-info-manifest-* 上传
        │
        ▼
record job（每次 run 一个）
  ├─ download-artifact（pattern: wheel-info-manifest-*，**不加 merge-multiple**）
  ├─ 合并全部 manifest → 一份
  └─ ./.github/actions/record-wheel-info
       └─ scripts/gen_wheel_info.py record --manifest … --workflow …
            └─ 改 packaging/wheel-info.yaml → 提交 → 开 review-gated PR
```

两个非显然的决定，改动时最容易踩：

- **一次 run 只有一个 committer。** 发布步骤自己不碰 `wheel-info.yaml`：
  矩阵扇出（`backend: all`）会有 N 个 leg 同时发布，各自开 PR 会互相打架。
  合并落在唯一的 record job 里，所以 N 路扇出仍然只有一个提交者。
- **download-artifact 不能加 `merge-multiple`。** 每个 leg 上传的 artifact 里
  文件名都是 `manifest.tsv`，展平到一个目录会互相覆盖，只剩一份。因此保持
  「一个 artifact 一个目录」，用 `.wheel-info-dl/*/*.tsv` 收集。

## 作业形态：reusable workflow + composite action

record job 的 job 体在所有 wheel workflow 里是同一份，抽成
`.github/workflows/record-wheel-info.yml`（`on: workflow_call`）。调用点只保留
**每个 workflow 各不相同**的三样东西：

```yaml
  record-wheel-info:
    needs: build
    if: ${{ always() && inputs.upload && !cancelled() }}
    permissions:
      contents: write
      pull-requests: write
    uses: ./.github/workflows/record-wheel-info.yml
    with:
      workflow: vllm        # → 分支 auto/wheel-info-vllm，也是 PR 里的出处名
```

- **`runs-on` 和 `steps` 不能在调用点出现。** 调用 job 只允许
  `name/uses/with/secrets/strategy/needs/if/concurrency/permissions/cache-mode`，
  所以作业体（checkout / download-artifact / 合并 / 调 composite action）全在
  called workflow 里。composite action `.github/actions/record-wheel-info/` 是
  更内层的一步：挑一个能 `import yaml` 的解释器（挑不到就装，装不上就报错退出）。
- **`permissions` 必须留在调用点。** 它是 record 能写仓库、能开 PR 的授权来源；
  called workflow 只能降权不能提权。
- **`if` 里的 `always()` 是必要的。** 中途失败的发布步骤留下的 manifest 仍然是
  「哪些包确实传上去了」的记录；同时 `always()` 保证被 skip 的 `needs` job 不会
  被误读成 success。真正的闸门是后半段的发布开关（`inputs.upload` / `inputs.publish`）。
- **`workflow:` 是输入，不能从 context 读。** called workflow 看到的
  `${{ github.workflow }}` 是**调用方**的名字；每个调用点显式传自己的出处名。

## 已接入 / 未接入

已接入（10 个）：`flagcx-wheel`、`flaggems-release`（python + cpp）、
`flash-attn-wheel`、`flaglibs-wheel`、`vllm-wheel`、`vllm-plugin-wheel`、
`sglang-wheel`（build + shim）、`sglang-plugin-wheel`、`megatron-wheel`、
`flagos-compressor-wheel`。

未接入，且**有意如此**：

- `flaggems-wheel`、`flagtree-wheel`、`flagtree-builder` —— 明确不接。
- `megatron-wheel` 的 provenance 构建（版本含 `+fl.<date>.g<sha>`）不记录：
  它不对应任何发布版本，只有带 `mlf_version` 的 release 发布才记。
- `torch-fl` 的 7 行没有对应流水线，继续手写。
- deb/rpm、`upload-nexus`、app 镜像、gendoc 各线不属本管线。

## 已知边界

- 文件是经 YAML dumper 写回的，所以**布局**（键序、列表缩进）由 dumper 决定：
  写在目录**内部**的注释撑不过一次 record，写在字段**值**上的文案能撑过。
  当前文件能逐字节 round-trip，这是要维持的性质，不是预期中的 diff。
- 没有 CI 漂移检查（原设计的 `render --check` 未做）。记录的触发点是发布，
  不是定时校验。

## 验证

- `record --dry-run` 打印 unified diff 且不落盘（写之前不改任何东西）。
- 手工核对过的行为：重复记录同一事件 ⇒ 无改动；真实合并 ⇒ 单个 `flagos-ci`
  提交 + 分支 `auto/wheel-info-<workflow>`；手写 `desc_zh` 逐字节不变、只有目标
  字段变化；`py3-none-any` 事件替换编译行的平台集。
- 10 个 workflow 的 manifest 步骤各自被抽出来、渲染 env、在临时目录跑过：
  15 个用例（含 megatron provenance 应记 0 行、flaggems-release 扇出 14 lane）
  全部通过，行格式为 4 个 tab 字段且 `record --dry-run` 接受合并结果。
