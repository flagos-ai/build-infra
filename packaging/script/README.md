# packaging/script/ — repack 工具

vllm / sglang 两条 repack 线共用的工具层，不属任何 app。

| 文件 | 作用 |
|---|---|
| `repack.py` | 改 wheel 的 METADATA（剥依赖、改版本号）、改 tag 与 dist-info 目录名，产出 `+flagos` wheel 与 `.deps-manifest.yaml` |
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

## tag

`repack.py` 沿用源 wheel 的 tag。源 wheel 的 tag 由 `setuptools-rust` 决定：
`rust_extensions()` 返回非空列表时 `has_ext_modules()` 为真，`bdist_wheel` 即产出
`cp3xx-cp3xx-<plat>`，与是否真的编出 `.so` 无关。沿用而非改写，是因为二进制子依赖
（如 opencv 的 `cp37-abi3`、xgrammar 的 `cp3xx`）的 tag 必须与文件名一致，pip 才会
按平台正确挑选。

解释器版本的下限与上限由 METADATA 的 `Requires-Python` 声明（来自上游
`pyproject.toml`），不由 tag 承担。

## 另见

- 剥除规则：`packaging/vllm/config.yaml`、`packaging/sglang/config.yaml`
- 构建与发布链：`packaging/<app>/build-and-repack.sh`、`.github/workflows/<app>-wheel.yml`
- wheel 目录的索引记录机制：`docs/wheel-info.md`
- native wheel（vllm-plugin-FL）的 tag 规则：`packaging/vllm/DESIGN.md`
