## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Kunlunxin P800
- **Host driver:** 5.37.1
- **Container toolkit** *(optional)*: xpu_container >= 1.0.13

## Image contents

### Base image

`ubuntu:22.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.9ubuntu3
- `ca-certificates` — 20260601~22.04.1
- `cmake` — 3.22.1
- `curl` — 7.81.0
- `g++` — 11.2.0
- `gcc` — 11.2.0
- `git` — 2.34.1
- `make` — 4.3
- `pciutils` — 3.7.0
- `unzip` — 6.0
- `vim` — 8.2.3995

### SDK components

- CUDA 12.9.0_575.51.03
- XRE-CUDA12 5.37.1.0
- XCUDART 5.13.0

## Environment

- `PATH=/usr/local/xpu/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/xpu/lib:/usr/local/xcudart/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime xpu \
  -e CXPU_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.37.1:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/xpu0 \
  --device /dev/xpuctrl \
  harbor.baai.ac.cn/flagos-base/flagos-base-kunlunxin-xre5.37.1:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
xpu-smi
```

*Last updated: 2026-10-14 13:43:56 · `393cfb81d50e`*

## Changelog

### 2.3.0

*2026-10-14 05:49:46*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-22 07:04:33*

- The vendor's xCCL and MPICH 3.3.2 are installed under `/usr/local` and
  named on `LD_LIBRARY_PATH` and `PATH`, so FlagCX's `bkcl` call sites
  resolve inside the container without a host mount.
- XRE and xcudart each install libxpuml, libxpucuda, libxpunvidia-ml,
  libcudart and libxpurt under identical names from builds of different
  generations, and which one a process picks up depends on how the library
  is reached — the xcudart copies lack symbols XRE's have. XRE's copy of
  each is installed over xcudart's; content, not version, is the test, and
  the step ends by asserting that no soname is shipped twice with different
  content.

### 2.1.2

*2026-08-14 14:35:51*

- First delivery: XRE 5.37.1 with CUDA 12.9.0 and XCUDART 5.13.0 on
  ubuntu:22.04.
