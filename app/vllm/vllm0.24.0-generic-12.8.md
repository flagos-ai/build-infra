## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Generic GPU
- **Host driver:** 610.43.02
- **Container toolkit** *(optional)*: nvidia-container-toolkit

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-nvidia-cuda12.8:2.3.0`

### Python

3.12

### Application package

`vllm==0.24.0+flagos`


`vllm-plugin-fl==0.3.0`

## Environment

- `VLLM_USE_FLASHINFER_SAMPLER=0`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-generic-12.8:2.3.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-generic-12.8:2.3.0-0.3.0
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
  $IMG vllm-serve --model <path> --port 9000
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
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.3.0-0.3.0

*2026-10-26 23:10:25*

- The runtime introduces two container-start flags,
  `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>`,
  which override the compiler and FlagGems versions baked into the image. A
  request that cannot be honoured stops the container instead of letting it
  run on another version.
- flagcx 0.14.0 is now a runtime dependency, pinned as
  flagcx==0.14.0+cuda12.8.
- This backend installs the native plugin build `0.3.0+cuda12.8`: it
  carries `vllm_fl._C` and registers `weak_ref_tensor` on the CUDA
  dispatch key, without which vLLM's cudagraph capture leaks VRAM
  per captured graph.

### 2.2.0-0.3.0

*2026-09-28 14:08:12*

The 0.24.0 line moves to the vllm-plugin-FL formal release v0.3.0 (tag = commit f105277). The plugin now ships as the release version (vllm-plugin-fl==0.3.0, one py3-none-any wheel, sha adf5a9e3...451f62, on every vendor index) instead of the v0.3.0-rc2.post2 delivery tag. Same stack and app pins as the rc2.post2 image it replaces; the only delta is the formal release of the same code.

### 2.2.0-0.3.0rc2.post2

*2026-09-20 09:58:26*

The NVIDIA image leaves the v0.3.0-rc0 tag, a 0.2.0-line build, for the 0.3.0 release line, so it now carries the plugin the rest of the 0.24.0 matrix is built on. Rebuilt on the FlagOS 2.2.0 stack, whose base and runtime carry FlagGems 5.4.0-rc2.post3, and on the vllm-plugin-FL release tag v0.3.0-rc2.post2 (0891073, head of 0.3.0-rc2): the plugin comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.0_ga9435a3.d20260821

*2026-08-24 06:04:48*

Initial vllm 0.24.0 deliverable on NVIDIA (repacked empty wheel, single-step install). Rust frontend components make the wheel ABI-bound to (python, arch); F/T dual-compiler E2E verified.
