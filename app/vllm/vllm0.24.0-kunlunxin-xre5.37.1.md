## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.37.1
- **Container toolkit** *(optional)*: xpu_container >= 1.0.13

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-kunlunxin-xre5.37.1:2.3.0`

### Python

3.10

### Application package

`vllm==0.24.0+flagos`


`vllm-plugin-fl==0.3.0`

## Environment

- `VLLM_FL_PLATFORM=kunlunxin`
- `VLLM_FL_PREFER=flagos`
- `USE_FLAGGEMS=1`
- `VLLM_FL_FLAGOS_WHITELIST=silu_and_mul,rms_norm,rotary_embedding`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-kunlunxin-xre5.37.1:2.3.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-kunlunxin-xre5.37.1:2.3.0-0.3.0
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  $IMG vllm-serve --model <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.3.0-0.3.0

*2026-10-26 23:13:33*

- The runtime introduces two container-start flags,
  `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>`,
  which override the compiler and FlagGems versions baked into the image. A
  request that cannot be honoured stops the container instead of letting it
  run on another version.
- flagcx 0.14.0 is now a runtime dependency, pinned as
  flagcx==0.14.0+xre5.37.1.
- This backend installs the native plugin build `0.3.0+xre5.37.1`: it
  carries `vllm_fl._C` and registers `weak_ref_tensor` on the CUDA
  dispatch key, without which vLLM's cudagraph capture leaks VRAM
  per captured graph.

### 2.2.0-0.3.0

*2026-09-28 14:02:40*

The 0.24.0 line moves to the vllm-plugin-FL formal release v0.3.0 (tag = commit f105277). The plugin now ships as the release version (vllm-plugin-fl==0.3.0, one py3-none-any wheel, sha adf5a9e3...451f62, on every vendor index) instead of the v0.3.0-rc2.post2 delivery tag. Same stack and app pins as the rc2.post2 image it replaces; the only delta is the formal release of the same code.

### 2.2.0-0.3.0rc2.post2

*2026-09-22 11:31:33*

Rebuilt on the refreshed kunlunxin base, which now keeps one generation of the five sonames XRE and xcudart both ship (libxpuml, libxpucuda, libxpunvidia-ml, libcudart, libxpurt) where it previously installed both. Two generations of one name were reachable at once: torch_plugin dlopens libxpuml.so.1 by absolute path out of the libcuda.so.1 directory, which is xcudart's copy, while the loader's default search and FlagCX's link line take XRE's, and the xcudart copy lacks nvml symbols the XRE one has. The runtime image this app is built on was rebuilt on that base and the app image carries it, so the mix would otherwise ship inside this image.

*2026-09-20 09:54:00*

The kunlunxin 0.24.0 port (PR 401) is on the release line now, so this image leaves f780db1, the pre-merge head of that port; the port carries the paged-KV write-convention fix and the FLA target re-point the previous image lacked. Rebuilt on the FlagOS 2.2.0 stack, whose base and runtime carry FlagGems 5.4.0-rc2.post3, and on the vllm-plugin-FL release tag v0.3.0-rc2.post2 (0891073, head of 0.3.0-rc2): the plugin comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.0_gf780db1.d20260823

*2026-08-23 04:47:16*

Initial vllm 0.24.0 deliverable on kunlunxin (PR 401). F/T verified.
