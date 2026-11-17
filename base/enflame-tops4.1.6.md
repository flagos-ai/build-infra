## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame L600
- **Host driver:** 4.1.6
- **Container toolkit** *(optional)*: tencent-container-toolkit >= 2.0.52

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
- `libelf1`
- `make` — 4.3
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- Enflame driver 4.1.6
- TOPS Runtime 4.1.6
- TOPS CC 4.1.6
- TOPSTX 4.1.6
- TOPS PTI 4.1.6
- TOPS ATen 4.1.20261111
- EFML 4.1.6
- ECCL 4.1.4
- ECCL Tests 4.1.4
- Gculare-perftest 4.1.6
- Triton GCU 1.0.20261116.cc.4.1.6

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops4.1.6:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops4.1.6:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```

*Last updated: 2026-11-17 21:15:48 · `328ab31fa07c`*

## Changelog

### 2.3.0

*2026-11-17 13:50:07*

- First delivery: the Enflame TopsPlatform 4.1.6 stack — driver, runtime,
  CC, PTI, TOPSTX, TOPS ATen, EFML, ECCL, Triton GCU 1.0.20261116 and
  gculare-perftest — on ubuntu:24.04, for the L600 chip.
- `/opt/triton_gcu` is a symlink to where the vendor's triton package
  installs, which is where FlagTree's `toolkit.py` looks for it.
