## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.1.1`

### Python

3.10

### Major Python packages

- `flag_gems`
- `torch==2.7.1+corex.4.4.0`
- `torchaudio==2.7.1+corex.4.4.0`
- `torchvision==0.22.1+corex.4.4.0`
- `triton==3.1.0+corex.4.4.0`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```
