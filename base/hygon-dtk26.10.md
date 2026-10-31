## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.4.2-V2.1.0
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260816ubuntu0.24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `libdrm-amdgpu1` — 2.4.125
- `libdw1`
- `libelf1`
- `libgfortran5` — 14.2.0
- `libgoogle-glog0v6t64` — 0.6.0
- `libibverbs1` — 50.0
- `libnuma1` — 2.0.18
- `libpciaccess0` — 0.17
- `libquadmath0` — 14.2.0
- `pciutils` — 3.10.0
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- Hygon DTK 26.10
- Hygon DTK LLVM

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.10:2.3.0 bash
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
  harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.10:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
hy-smi
```

*Last updated: 2026-10-31 13:41:54 · `115dccef47d6`*

## Changelog

### 2.3.0

*2026-10-31 07:11:14*

- ROCm-aware Open MPI 5.0.8 is installed from
  `flagos-filestore/hygon/openmpi-rocm_5.0.8-1_jammy_amd64.deb`,
  checksum-pinned. `libtorch_cpu.so` references
  `MPIX_Query_rocm_support`, which only Open MPI 5.x's `mpiext/rocm`
  component exports and only when built `--with-rocm`; Ubuntu's 4.1.x
  cannot satisfy it, so `import torch` fails with an undefined symbol.
- `libibverbs1` and `libquadmath0` join the apt layer: `libtorch_cpu.so`
  NEEDs the former directly, and the MKL libraries torch ships NEED the
  latter.

*2026-10-29 09:41:24*

- First delivery: Hygon DTK 26.10 on ubuntu:24.04. DTK 26.10 ships a
  native Ubuntu-24.04 build, so this image takes it directly instead of
  the 26.04 line's 22.04 forward-compat path.
- The dtk_llvm (aillvm) overlay installs into `/opt/dtk-26.10` alongside
  the SDK, matching the 26.04 base image's toolchain layout.
