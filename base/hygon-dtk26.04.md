## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `git`
- `libdrm-amdgpu1`
- `libdw1`
- `libelf1`
- `libgfortran5`
- `libgoogle-glog0v6t64`
- `libnuma1`
- `libpciaccess0`
- `pciutils`
- `unzip`
- `vim`

### SDK components

- Hygon DTK 26.04
- Hygon DTK LLVM

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
hy-smi
```

## Changelog

### 2.3.0

*2026-10-27 02:02:24*

- `libgoogle-glog0v6t64` is installed for the `libglog.so.1` soname: torch's
  c10 headers make an extension build link glog (`C10_USE_GLOG`) and DTK
  ships no such library, so `import vllm_fl._C` failed and this backend's
  application layer could not load its native plugin.

### 2.2.0

*2026-09-17 01:20:40*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.1.2

*2026-08-16 03:44:50*

- First delivery: Hygon DTK 26.04 with the DTK LLVM toolchain on
  ubuntu:24.04. The DTK build is the Ubuntu 22.04 one — there is no 24.04
  release — and the image takes the newer base for the libstdc++ FlagTree
  needs.
- The DTK LLVM package ships in it — the toolchain FlagTree's DCU backend
  builds against.
- `libnuma1`, `libgfortran5`, `libdrm-amdgpu1`, `libdw1`, `libelf1` and
  `libpciaccess0` carry the userspace the torch build and the DCU detection
  path need.
- The SDK environment is captured into `/etc/profile.d/vendor.sh` at build
  time; `env.sh` runs under bash because it finds DTKROOT through
  `BASH_SOURCE[0]`, which dash does not support.
