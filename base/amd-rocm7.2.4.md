## Prerequisites

- **Architecture:** x86_64
- **Chip models:** AMD Radeon PRO W7900
- **Host driver:** 6.16.13
- **Container toolkit** *(optional)*: amd-container-toolkit >= 1.3.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `amd-smi-lib` — 26.2.2.70204
- `amdgpu-core` — 7.2.07020400
- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260816ubuntu0.24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `gnupg` — 2.4.4
- `hip-dev` — 7.2.53211.70204
- `hipblas-dev` — 3.2.0.70204
- `hipblaslt-dev` — 1.2.2.70204
- `hipcc` — 1.1.1.70204
- `hipcub-dev` — 4.2.0.70204
- `hipfft-dev` — 1.0.22.70204
- `hiprand-dev` — 3.1.0.70204
- `hipsolver-dev` — 3.2.0.70204
- `hipsparse-dev` — 4.2.0.70204
- `hipsparselt-dev` — 0.2.6.70204
- `hsa-amd-aqlprofile` — 1.0.0.70204
- `hsa-rocr-dev` — 1.18.0.70204
- `libdw1`
- `libelf1`
- `libgfortran5` — 14.2.0
- `libnuma1` — 2.0.18
- `libpciaccess0` — 0.17
- `miopen-hip-dev` — 3.5.1.70204
- `pciutils` — 3.10.0
- `rccl-dev` — 2.27.7.70204
- `rocblas-dev` — 5.2.0.70204
- `rocfft-dev` — 1.0.36.70204
- `rocm-cmake` — 0.14.0.70204
- `rocm-device-libs` — 1.0.0.70204
- `rocm-llvm` — 22.0.0.26084.70204
- `rocm-smi-lib` — 7.8.0.70204
- `rocm-utils` — 7.2.4.70204
- `rocminfo` — 1.0.0.70204
- `rocprofiler-register` — 0.6.0.70204
- `rocrand-dev` — 4.2.0.70204
- `rocsolver-dev` — 3.32.0.70204
- `rocsparse-dev` — 4.2.0.70204
- `rocthrust-dev` — 4.2.0.70204
- `roctracer` — 4.1.70204.70204
- `rocwmma-dev` — 2.2.0.70204
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- ROCm 7.2.4 (x86_64)

## Environment

- `ROCM_PATH=/opt/rocm`
- `PATH=/opt/rocm/bin:$PATH`
- `LD_LIBRARY_PATH=/opt/rocm/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime amd \
  --device /dev/kfd \
  --device /dev/dri \
  harbor.baai.ac.cn/flagos-base/flagos-base-amd-rocm7.2.4:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/dri \
  --group-add video \
  --security-opt seccomp=unconfined \
  harbor.baai.ac.cn/flagos-base/flagos-base-amd-rocm7.2.4:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
rocm-smi
```

*Last updated: 2026-10-31 19:30:38 · `f96d3762740e`*

## Changelog

### 2.3.0

*2026-10-31 12:10:39*

Drop the `HIP_VISIBLE_DEVICES=all` ENV. HIP 7.2 accepts device ordinals or GPU-UUIDs and nothing else, so this value — the NVIDIA-style spelling — parsed to an empty device list: `hipGetDeviceCount()` and therefore `torch.cuda.device_count()` returned 0, while `rocm-smi` inside the same container listed every GPU. The variable being unset means all devices, which is what the ENV was trying to say, so the image now defaults to the full device set and a single-GPU pin uses `-e HIP_VISIBLE_DEVICES=<n>`.

*2026-10-27 07:58:45*

- First delivery: ROCm 7.2.4 for gfx1100 (RDNA3, Radeon PRO W7900) on
  ubuntu:24.04 — the runtime set plus the `-dev` packages the compiler stack
  links against.
- ROCm comes from `repo.radeon.com` rather than a filestore tarball, so the
  image takes the point releases that repository serves at build time. A pin
  holds radeon's `rocm-cmake`, `hipcc` and `rocminfo` ahead of the older
  builds Ubuntu universe also carries. The DKMS kernel driver is not
  installed — the host provides the device.
- `hipsolver-dev`, `hipfft-dev` and `miopen-hip-dev` are installed although
  torch and vLLM link none of them: torch's own headers include theirs under
  `USE_ROCM`, so an extension build — the flagcx torch wheel among them —
  fails without them.
