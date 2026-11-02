# thead（平头哥）

backend key：`thead-ppu2.0.0`（T-Head ZW810E）。**只有 config，没有 base 镜像**。

## 现状

没有 `base/thead-*`，因为该芯片**当前只有阿里云 PAI 平台的容器镜像** —— PAI 的
镜像形态不能直接作为 FlagOS base 使用。要出 FlagOS base 镜像需要与 PAI 团队
协作，属外部依赖，不是本仓库待补的活。

因此 `thead-ppu2.0.0` 不出现在 CI 矩阵里。`configs.yaml` 里的条目
（`torch==2.9.0+ppu2.0.0.oe`、`triton==3.5.0+ppu2.0.0.oe`、`extras: thead`、
`python 3.12`）是依赖事实源，保留待用。

## 指针

- `configs.yaml` `vendors.thead.ppu2.0.0`
- `scripts/verify-nodes.example.yaml` 里留着 `thead-ppu2.0.0: thead` 别名，
  镜像可用之前它没有实际用途
