## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.9.29
- **Container toolkit** *(optional)*: tencent-container-toolkit >= 2.0.52

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `cmake` — 3.28.3
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `libelf1`
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- Enflame driver 1.9.29
- TOPS Runtime 1.9.29
- TOPS CC 1.9.29
- TOPS PTI 1.9.29
- TOPSTX 1.9.29
- TOPS ATen 3.8.20261009
- EFML 1.9.29
- ECCL 3.6.3.13
- Triton GCU 1.0.20261116.cc.1.9.29
- Gculare-perftest 1.9.29

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.29:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.29:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```

*Last updated: 2026-11-17 18:18:40 · `c4048698ec3e`*

## Changelog

### 2.3.0

*2026-11-17 10:33:53*

- First delivery: the Enflame TopsPlatform 1.9.29 stack — driver, runtime,
  CC, PTI, TOPSTX, TOPS ATen, EFML, ECCL, Triton GCU 1.0.20261116 and
  gculare-perftest — on ubuntu:24.04, for the Zixiao C200 (S60) chip.
- `/opt/triton_gcu` is a symlink to where the vendor's triton package
  installs, which is where FlagTree's `toolkit.py` looks for it.
