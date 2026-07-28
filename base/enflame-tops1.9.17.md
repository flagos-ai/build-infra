## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.9.17
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
- `make` — 4.3
- `vim` — 9.1.0016

### SDK components

- Enflame driver 1.9.17
- TOPS Runtime 1.9.17
- TOPS CC 1.9.17
- TOPS PTI 1.9.17
- TOPSTX 1.9.17
- TOPS ATen 3.7.20260602
- EFML 1.9.17
- ECCL 3.6.3.11
- ECCL Tests 3.6.3.11
- Triton GCU 3.6.0+1.0.20260610.cc.1.9.17
- Gculare-perftest 1.9.17

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.17:2.1.1 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.17:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```
