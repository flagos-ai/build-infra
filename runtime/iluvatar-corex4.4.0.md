## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.2`

### Python

3.12

### Major Python packages

- `flag_gems==5.3.5`
- `flagtree==0.6.1+iluvatar3.6`
- `numpy==1.26.4`
- `torch==2.7.1+corex.4.4.0`
- `torchaudio==2.7.1+corex.4.4.0`
- `torchvision==0.22.1+corex.4.4.0`
- `triton==3.1.0+corex.4.4.0` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```
