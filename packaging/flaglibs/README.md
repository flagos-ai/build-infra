# packaging/flaglibs/ — FlagOS 算子库 wheel 发布

发布 6 个纯 Python FlagOS 算子库的可安装 wheel 到 `flagos-pypi-hosted`。

## 覆盖范围

| 包 | 上游仓库 | default_ref (release tag) | 版本来源 |
|---|---|---|---|
| `flag_attn` | FlagAttention | v0.4.0 | setuptools_scm（git tag） |
| `flagsparse` | FlagSparse | v0.3.0 | pyproject 静态 |
| `flag_blas` | FlagBLAS | v0.3.0 | pyproject 静态 |
| `flag_audio` | FlagAudio | v0.3.0 | pyproject 静态 |
| `flagfft-codegen` | FlagFFT | v0.2.0 | pyproject 静态 |
| `flaggems_vllm` | FlagGems-vllm | v0.2.0 | pyproject 静态 |

不在范围：FlagDNN（无 Python 打包）、FlagTensor（csrc 未接入 setuptools）——
上游改造后按本骨架扩展。

## 使用

```bash
# 全部 6 库构建到 ./wheels
bash packaging/flaglibs/build.sh

# 指定子集 + 输出目录 + 单库 ref 覆盖
FLAGLIBS="flag_attn flagsparse" \
OUTDIR=/tmp/wheels \
REF_flag_attn=v0.4.0 \
bash packaging/flaglibs/build.sh
```

构建只在 CI 跑（`.github/workflows/flaglibs-wheel.yml`，manual dispatch）——
见 `docs/decisions.md` 的自动化边界。

## 文件

- `build.sh` — 6 库构建（clone → venv → `pip wheel --no-deps`），py3-none-any 门禁
- `build-config.yaml` — 6 库清单（repo / default_ref / scm 标记）
- `docs/decisions.md` — 决策记录（版本来源、hosted 而非 per-vendor、tag-vs-pyproject 不一致）

## 现状

- 版本归一（动态 `__version__` + 去 scikit-build-core + changelog）已全数合入上游 main 与 rc2。
- 6 个 release tag 已与各自 rc2 head 对齐。
- **6 个 wheel 已发布到 `flagos-pypi-hosted`**（2026-09-28，CI run 36425218655）：index 已确认各版本在列（`flag-attn 0.4.0` / `flagsparse 0.3.0` / `flag-blas 0.3.0` / `flag-audio 0.3.0` / `flagfft-codegen 0.2.0` / `flaggems_vllm 0.2.0`），`pip download` 全部可拉取。之后上游 tag 移动时重新触发 `flaglibs-wheel.yml`（upload=true）。
