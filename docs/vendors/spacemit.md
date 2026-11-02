# spacemit（进迭时空）

backend key：`spacemit-spacemit`。**只有 config，没有容器**。

## 现状

`configs.yaml` 里存在这个 vendor，作用是**依赖的事实源**（`extras: spacemit`、
`torch==2.8.0+spacemit.0`、`triton==3.6.0+spacemit.a5`、`python 3.12`），
但仓库里**没有 `base/spacemit-*`**，所以它不可构建，也不进任何 CI 矩阵。

这是**有意保留**，不是遗漏 —— 等有了容器化方案再启用。看到它在 configs.yaml 里
而没有镜像时不要当成 bug 去补 base 文件。

## 指针

- `configs.yaml` `vendors.spacemit`
- 判断某 backend 是否可构建：`python scripts/generate_matrix.py`（它只列 buildable 的）
