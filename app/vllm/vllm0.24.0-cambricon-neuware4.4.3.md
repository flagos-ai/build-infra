## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.2.15

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.4.3:2.3.0`

### Python

3.10

### Application package

`vllm==0.24.0+flagos`


`vllm-plugin-fl==0.3.0`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/vllm0.24.0-cambricon-neuware4.4.3:2.3.0-0.3.0`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/vllm0.24.0-cambricon-neuware4.4.3:2.3.0-0.3.0
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  $IMG vllm-serve --model <path> --port 9000
```

## Changelog

### 2.3.0-0.3.0

*2026-10-26 12:51:21*

- The runtime introduces two container-start flags,
  `-e FLAGTREE_VERSION=<ver|latest>` and `-e FLAGGEMS_VERSION=<ver|latest>`,
  which override the compiler and FlagGems versions baked into the image. A
  request that cannot be honoured stops the container instead of letting it
  run on another version.
- flagcx 0.14.0 is now a runtime dependency, pinned as
  flagcx==0.14.0+neuware4.4.3.

### 2.2.0-0.3.0

*2026-09-28 14:29:07*

The 0.24.0 line moves to the vllm-plugin-FL formal release v0.3.0 (tag = commit f105277). The plugin now ships as the release version (vllm-plugin-fl==0.3.0, one py3-none-any wheel, sha adf5a9e3...451f62, on every vendor index) instead of the v0.3.0-rc2.post2 delivery tag. Same stack and app pins as the rc2.post2 image it replaces; the only delta is the formal release of the same code.

### 2.2.0-0.3.0rc2.post2

*2026-09-20 10:20:43*

The MLU590 / neuware 4.4.3 port (PR 431) is on the release line now, so this image leaves ea38c86, a 0.2.1-line commit. Rebuilt on the FlagOS 2.2.0 stack, whose base and runtime carry FlagGems 5.4.0-rc2.post3, and on the vllm-plugin- FL release tag v0.3.0-rc2.post2 (0891073, head of 0.3.0-rc2): the plugin comes from a released tag rather than a pre-merge commit — an immutable pin, and one wheel served by every vendor index.

### 2.1.2-0.2.1_gea38c86.d20260902

*2026-09-02 10:10:22*

Initial vllm 0.24.0 deliverable on cambricon 4.4.3 via vllm-plugin-FL PR 431 (MLU590/4.4.3 port to main). F path verified.
