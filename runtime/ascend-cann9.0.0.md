## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 26.0.rc1
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann9.0.0:2.1.1`

### Python

3.11

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0+ascend3.5`
- `torch-npu==2.10.0`
- `torch==2.10.0+cpu`
- `triton==3.5.0 (+ triton_ascend==3.2.1)` *(fallback)*

*Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).*

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann9.0.0:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann9.0.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh && npu-smi info
```
