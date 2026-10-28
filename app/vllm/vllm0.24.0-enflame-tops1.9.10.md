## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.9.10
- **Container toolkit** *(optional)*: tencent-container-toolkit >= 2.0.52

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.9.10:2.3.0`

### Python

3.12

### Application package

`vllm==0.24.0+flagos`


`vllm-plugin-fl==0.3.0`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-enflame-tops1.9.10:2.3.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-enflame-tops1.9.10:2.3.0-0.3.0
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  $IMG vllm-serve --model <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.3.0-0.3.0

*2026-10-26 12:21:47*

- The runtime introduces two container-start flags,
  `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>`,
  which override the compiler and FlagGems versions baked into the image. A
  request that cannot be honoured stops the container instead of letting it
  run on another version.
- flagcx 0.14.0 is now a runtime dependency, pinned as
  flagcx==0.14.0+tops1.9.10.

### 2.2.0-0.3.0

*2026-09-28 14:03:57*

The 0.24.0 line moves to the vllm-plugin-FL formal release v0.3.0 (tag = commit f105277). The plugin now ships as the release version (vllm-plugin-fl==0.3.0, one py3-none-any wheel, sha adf5a9e3...451f62, on every vendor index) instead of the v0.3.0-rc2.post2 delivery tag. Same stack and app pins as the rc2.post2 image it replaces; the only delta is the formal release of the same code.

### 2.2.0-0.3.0rc2.post2

*2026-09-20 09:55:48*

The GCU300 enablement bundle (PR 432) is on the release line now, so this image leaves 7c6758c, the pre-merge head of that port. Rebuilt on the FlagOS 2.2.0 stack, whose base and runtime carry FlagGems 5.4.0-rc2.post3, and on the vllm-plugin-FL release tag v0.3.0-rc2.post2 (0891073, head of 0.3.0-rc2): the plugin comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.1_g7c6758c.d20260903

*2026-09-03 15:20:20*

Initial vllm 0.24.0 deliverable on enflame (PR 432 GCU300 port to main). F/T verified.
