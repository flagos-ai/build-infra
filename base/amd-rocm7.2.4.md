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

- `amd-smi-lib`
- `amdgpu-core`
- `build-essential`
- `ca-certificates`
- `cmake`
- `curl`
- `g++`
- `gcc`
- `git`
- `gnupg`
- `hip-dev`
- `hipblas-dev`
- `hipblaslt-dev`
- `hipcc`
- `hipcub-dev`
- `hipfft-dev`
- `hiprand-dev`
- `hipsolver-dev`
- `hipsparse-dev`
- `hipsparselt-dev`
- `hsa-amd-aqlprofile`
- `hsa-rocr-dev`
- `libdw1`
- `libelf1`
- `libgfortran5`
- `libnuma1`
- `libpciaccess0`
- `miopen-hip-dev`
- `pciutils`
- `rccl-dev`
- `rocblas-dev`
- `rocfft-dev`
- `rocm-cmake`
- `rocm-device-libs`
- `rocm-llvm`
- `rocm-smi-lib`
- `rocm-utils`
- `rocminfo`
- `rocprofiler-register`
- `rocrand-dev`
- `rocsolver-dev`
- `rocsparse-dev`
- `rocthrust-dev`
- `roctracer`
- `rocwmma-dev`
- `unzip`
- `vim`

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
