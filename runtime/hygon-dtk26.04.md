## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-hygon-dtk26.04:2.1.1`

### Python

3.10

### Major Python packages

- `flag_gems`
- `flagtree==0.5.1+hcu3.1`
- `torch==2.9.0+das.opt1.dtk2604`
- `triton==3.3.0+das.opt1.dtk2604.torch290` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:latest bash
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
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
source /opt/hyhal/env.sh && hy-smi
```
