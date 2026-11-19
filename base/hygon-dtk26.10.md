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
- `ca-certificates` — 20260816ubuntu0.24.04.2
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
- Hygon DTK AICC LLVM

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

*Last updated: 2026-11-16 19:12:48 · `81bbee1afa57`*

## Changelog

### 2.3.0

*2026-11-19 13:57:30*

- `vendor.sh` no longer overwrites a caller's `PYTHONPATH`: it now
  prepends the SDK paths only when they are absent, keeping any path the
  container was started with (#1866).
- Non-interactive bash loads `vendor.sh` through `BASH_ENV`, so the old
  absolute `export` dropped the caller's entries before Python ever ran
  and broke imports that depended on them.

*2026-11-16 12:09:45*

- The clang-18 aillvm comes from `dtk_llvm-1.0.0+dtk2604.2609221416.g5f9d5e`
  instead of the bare `dtk_llvm.run`. Both builds' clang-18 parse FlagTree's
  IR apart from one intrinsic: `dtk_llvm.run`'s takes only i32
  `numRecords` in `llvm.amdgcn.make.buffer.rsrc`, this one only i64, and
  the runtime's FlagTree moves to 0.7.1a1, whose hcu kernels emit i64.
  Any other pairing fails with `Intrinsic has incorrect argument type`.

*2026-11-04 11:35:10*

- The aicc aillvm package joins `dtk_llvm.run`, so the image now carries
  clang-18 and clang-22 side by side and the vendor triton 3.7.0 can
  compile again. Two compiler paths need one each: vendor triton 3.7.0
  passes clang-22-only flags and emits clang-22-only IR, while FlagTree's
  bundled libtriton emits IR that only clang-18 parses. Either clang
  alone leaves one of the two paths red.
- Both LLVM installers are now checksum-pinned, like the Open MPI
  package in this image, and the step asserts that clang-18, clang-22
  and MLIRConfig.cmake all landed.

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
