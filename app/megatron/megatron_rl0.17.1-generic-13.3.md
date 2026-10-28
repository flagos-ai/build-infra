## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Generic GPU
- **Host driver:** 610.43.02
- **Container toolkit** *(optional)*: nvidia-container-toolkit

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda13.3:2.2.0`

### Python

3.12

### Application package

`megatron-core[rl]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-generic-13.3:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-generic-13.3:2.2.0-0.2.3
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --gpus all \
  $IMG bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.


### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  $IMG bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.

## Changelog

### 2.2.0-0.2.3

*2026-09-28 05:24:48*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-23 13:59:20*

Rebuild on the FlagOS 2.2.0 stack with the release-line wheel, pinned exactly (0.17.1+fl.0.2.3). The image this replaces was built on 2.1.2 from a wheel taken off the MLF PR heads and an integration branch, so the platform fixes those PRs carry were never in the artifact. flash_attn stays an app-layer dep here: it is not a runtime dep on this backend and the wheel is source-built with the ABI locked to this backend's torch.

### 2.1.2-0.2.1_9.g48b97a13f

*2026-08-20 02:18:47*

megatron-core RL wheel app image (MLF PR 114 RL extra + PR 119). Single-step wheel install over the runtime.
