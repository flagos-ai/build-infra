## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Hygon BW1000
- **Host driver:** 6.3.30-V1.4.1a
- **Container toolkit** *(optional)*: dcu-container-toolkit >= 1.3.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:2.2.0`

### Python

3.10

### Application package

`vllm==0.20.2+flagos`


`vllm-plugin-fl==0.2.2`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.20.2-hygon-dtk26.04:2.2.0-0.2.2`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.20.2-hygon-dtk26.04:2.2.0-0.2.2
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  -e DCU_VISIBLE_DEVICES=all \
  $IMG vllm-serve --model <path> --port 9000
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/mkfd \
  --device /dev/dri \
  --group-add video \
  -v /opt/hyhal:/opt/hyhal \
  --security-opt seccomp=unconfined \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.2.0-0.2.2

*2026-09-28 06:37:38*

Rebuild on the vllm-plugin-FL formal release v0.2.2 (tag = commit 675548ab, the head of 0.2.2-rc2). The plugin now ships as the release version (vllm-plugin-fl==0.2.2, one py3-none-any wheel, sha 90a4ba10...27fa2, on all 11 vendor indexes) instead of the v0.2.2-rc2.post2 delivery tag — the only delta is the backport of #553 (bounded/safe multiprocessing worker shutdown), which the 2.2.0 stack line now carries. App image rebuilt from that wheel, pinned exactly.

### 2.2.0-0.2.2rc2.post2

*2026-09-20 10:56:29*

Rebuild on the FlagOS 2.2.0 stack and on the vllm-plugin-FL release tag v0.2.2-rc2.post2 (214804a, head of 0.2.2-rc2). Both layers move at once: the stack brings the 2.2.0 base and runtime, with FlagGems 5.4.0-rc2.post3 and the 0.7.0-era FlagTree, and the plugin now comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.2rc2.post1_g52949b6.d20260914

*2026-09-14 03:59:20*

Rebuild on the vllm-plugin-FL v0.2.2-rc2.post1 tag (release/0.2 head 52949b6) to validate the tag on Hygon. The wheel version base follows the tag's own version (0.2.2rc2.post1) rather than the 0.2.1 line every earlier app image carried.

### 2.1.2-0.2.1_g14cf11d.d20260908

*2026-09-09 00:06:07*

vllm 0.20.2 on Hygon DTK 26.04 (CUDA-alias runtime). Built on the flagtree hygon wheel rebuild line with the vllm-plugin-FL hygon enablement; repacked vllm wheel single-step install. F/T verified.
