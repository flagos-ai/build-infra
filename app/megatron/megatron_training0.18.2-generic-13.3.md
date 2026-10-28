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

`megatron-core[training]==0.18.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_training0.18.2-generic-13.3:2.2.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_training0.18.2-generic-13.3:2.2.0-0.3.0
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --gpus all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --gpus all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --gpus all \
  $IMG megatron-train --model-type GPT
```

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

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/nvidia0 \
  --device /dev/nvidiactl \
  --device /dev/nvidia-uvm \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  -v /usr/lib/x86_64-linux-gnu/libcuda.so.1:/usr/lib/x86_64-linux-gnu/libcuda.so.1:ro \
  $IMG megatron-train --model-type GPT
```

## Changelog

### 2.2.0-0.3.0

*2026-09-27 12:42:44*

Rebuild on the re-pointed MLF v0.3.0 wheel (128dbd4f3), which now carries MLF #194 (flag_gems paged fallback for CUDA-facing accelerator builds). The 0.18.2 wheel and app images installed the pre-#194 wheel; the fix matters for this image because RL E2E on metax runs the flag_gems paged kernel via the lifted flash-attn gate.

*2026-09-27 09:44:08*

True rebuild on the re-tagged MLF v0.3.0 wheel (213d05856): the first round-2 push re-used the cached pip layer, so the image still carries the pre-#192/#193 wheel. This build runs --no-cache (push=false verify pass first), so the vendor index is resolved fresh and the installed wheel is the post-merge one.

*2026-09-27 08:36:23*

Rebuild on the re-tagged MLF v0.3.0 wheel, which now carries MLF #192 (NullTokenizer bos / local-impl packed-seq guard) and #193 (capability-based paged-attention dispatch for non-NPU platforms). The 0.18.2 app images installed the pre-#192/#193 wheel; the fix matters for this image because RL E2E on the non-NPU backends runs the platform paged kernel.

*2026-09-26 14:48:20*

First megatron-core 0.18.2 app image on the FlagOS 2.2.0 stack. Built from the MLF v0.3.0 tag (full-scope wheel, MLF #189) on the flagcx-fixed runtime, whose flagcx wheel's libflagcx_device.bc parses in flagtree's reader.
