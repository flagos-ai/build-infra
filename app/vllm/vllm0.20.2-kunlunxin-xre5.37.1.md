## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.37.1
- **Container toolkit** *(optional)*: xpu_container >= 1.0.13

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-kunlunxin-xre5.37.1:2.2.0`

### Python

3.10

### Application package

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Environment

- `VLLM_FL_PLATFORM=kunlunxin`
- `VLLM_FL_PREFER=flagos`
- `USE_FLAGGEMS=1`
- `VLLM_FL_FLAGOS_WHITELIST=silu_and_mul,rms_norm,rotary_embedding`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-kunlunxin-xre5.37.1:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-kunlunxin-xre5.37.1:2.2.0-0.2.2
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

### 2.2.0-0.2.2

*2026-09-28 06:32:30*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-22 11:42:17*

Rebuilt on the refreshed kunlunxin base, which now keeps one generation of the five sonames XRE and xcudart both ship (libxpuml, libxpucuda, libxpunvidia-ml, libcudart, libxpurt) where it previously installed both. Two generations of one name were reachable at once: torch_plugin dlopens libxpuml.so.1 by absolute path out of the libcuda.so.1 directory, which is xcudart's copy, while the loader's default search and FlagCX's link line take XRE's, and the xcudart copy lacks nvml symbols the XRE one has. The runtime image this app is built on was rebuilt on that base and the app image carries it, so the mix would otherwise ship inside this image.

*2026-09-20 10:54:30*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and the 0.7.0-era FlagTree, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.1_g8236c0a.d20260821

*2026-08-21 03:11:21*

Initial 0.20.2 deliverable on Kunlunxin P800 XPU. vllm-plugin-FL PR 268 kunlunxin enablement plus the decode-scale fix (PR 400: adjusted attention scale for decode via prefill_attention). Single-step install matrix-inert.
