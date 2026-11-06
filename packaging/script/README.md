# packaging/script/ — repack 工具

vllm / sglang 两条 repack 线共用的工具层，不属任何 app。

| 文件 | 作用 |
|---|---|
| `repack.py` | 改 wheel 的 METADATA（剥依赖、改版本号）、定 tag 与 dist-info 目录名、回写 RECORD，产出 `+flagos` wheel 与 `.deps-manifest.yaml` |
| `audit-deps.py` | wheel 依赖审计门；CI 在 `vllm-wheel.yml` / `sglang-wheel.yml` / `*-plugin-wheel.yml` 内调用 |

## 流程

```
上游 sdist ──→ 后端 runtime 镜像内 VLLM_TARGET_DEVICE=empty 构建
           ──→ repack.py + packaging/<app>/config.yaml 的剥除规则
           ──→ +flagos wheel
           ──→ 上传到 flagos-pypi-<vendor>
           ──→ app 镜像 pip install "vllm==<ver>+flagos"
```

调用方是 `packaging/<app>/build-and-repack.sh`（本地）与
`.github/workflows/<app>-wheel.yml`（CI），两者跑的是同一条链。

剥除规则按 app 分：`packaging/<app>/config.yaml` 是权威处，文件头写了每条规则的
判据。repack 不做任何硬件相关的构建——各后端产物同为 empty wheel，差异只在
vendor 镜像提供的解释器与架构。

## tag 与 RECORD

tag 由 wheel 成员判定，不由源 wheel 的 `Tag` 决定：`setuptools-rust` 只要声明了
Rust 扩展就按**构建**解释器打 tag，与是否真编出 `.so` 无关——vllm 的 empty 构建
无 cargo，产物 0 `.so`、0 `.data/`，却带 `Tag: cp312-cp312-linux_x86_64`，把
`Requires-Python` 已放行的解释器拒之门外。有平台相关成员的 wheel 保留源 tag
（opencv 的 `cp37-abi3`、xgrammar 的 `cp3xx`）——二进制子依赖的 tag 必须与文件名
一致，pip 才会按平台正确挑选；纯 Python 的落 `py3-none-any`。

解释器版本的下限与上限由 METADATA 的 `Requires-Python` 声明（来自上游
`pyproject.toml`），不由 tag 承担。

dist-info 目录改名、METADATA/WHEEL 重写之后，RECORD 由 repack 一并回写（改名、
重算、丢弃无对应成员的行），写完再按 RECORD 校验一遍产物。`pip install` 自己重算
RECORD，受影响的只是按 RECORD 做完整性校验或手工解包的路径。

## 另见

- 剥除规则：`packaging/vllm/config.yaml`、`packaging/sglang/config.yaml`
- 构建与发布链：`packaging/<app>/build-and-repack.sh`、`.github/workflows/<app>-wheel.yml`
- wheel 目录的索引记录机制：`docs/wheel-info.md`
- native wheel（vllm-plugin-FL）的 tag 规则：`packaging/vllm/DESIGN.md`
