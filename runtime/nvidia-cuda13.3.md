## Prerequisites

- **Architecture:** x86_64
- **Chip models:** NVIDIA H20
- **Host driver:** 610.43.02
- **Container toolkit** *(optional)*: nvidia-container-toolkit

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.3:2.2.0`

### Python

3.12

### Major Python packages

- `flag_gems==5.4.0`
- `flagcx==0.14.0rc2.post2+cuda13.3`
- `flagtree==0.7.0`
- `numpy==1.26.4`
- `torch==2.11.0+cu130`
- `torchaudio==2.11.0+cu130`
- `torchvision==0.26.0+cu130`
- `triton==3.6.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Environment

- `USE_FLAGTUNE_COST_MODEL=0`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --gpus all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:2.2.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:2.2.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
nvidia-smi
```
