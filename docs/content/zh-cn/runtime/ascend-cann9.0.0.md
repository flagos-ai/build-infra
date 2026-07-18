---
title: "ascend-cann9.0.0"
---

## 前置条件

- **架构:** aarch64
- **芯片型号:** Ascend 910B
- **宿主机驱动:** 26.0.rc1
- **容器工具包** <em>(可选)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装" aria-label="仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装">&#9432;</button>: Ascend-docker-runtime >= 6.0.RC3

## 镜像内容

### 基于

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.0.0:2.1.1-30-gd767fb5`

### Python

3.11

### 主要 Python 软件包

- `flag_gems`
- `flagtree==0.6.0+ascend3.5`
- `torch-npu==2.10.0`
- `torch==2.10.0+cpu`
- <span class="muted"><code class="plain">triton==3.5.0 (+ triton_ascend==3.2.1)</code></span>

<p class="muted"><em>灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。</em></p>

## 启动

**使用容器工具包** *(可选)*：

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  flagos-runtime-ascend-cann9.0.0:latest bash
```

**无需工具包** —— 直接使用 docker / podman：

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  flagos-runtime-ascend-cann9.0.0:latest bash
```

## 验证

在容器内，确认加速器可见：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh && npu-smi info
```
