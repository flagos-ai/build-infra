## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910C
- **Host driver:** 25.5.0
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0-910c:2.1.2`

### Python

3.11

### Major Python packages

- `attrs==24.2.0`
- `decorator==5.1.1`
- `flag_gems==5.3.5`
- `flagtree==0.6.0+ascend3.2`
- `numpy==1.26.4`
- `psutil==6.0.0`
- `torch-npu==2.9.0`
- `torch==2.9.0+cpu`
- `torchaudio==2.9.0`
- `torchvision==0.24.0`
- `triton-ascend==3.2.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann8.5.0-910c:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci1 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann8.5.0-910c:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
npu-smi info
```
