## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** *(optional)*: ix-container-toolkit >= 1.1.0

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `build-essential` — 12.10ubuntu1
- `ca-certificates` — 20260601~24.04.1
- `curl` — 8.5.0
- `g++` — 13.2.0
- `gcc` — 13.2.0
- `git` — 2.43.0
- `unzip` — 6.0
- `vim` — 9.1.0016

### SDK components

- Corex Runtime 4.4.0
- CUDA Header files 260604
- CMake (Iluvatar) 3.31.8

## Environment

- `COREX_ROOT=/usr/local/corex`
- `PATH=/usr/local/corex/bin:$PATH`
- `LD_LIBRARY_PATH=/usr/local/corex/lib`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.3.0 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  --device /dev/itrctl \
  harbor.baai.ac.cn/flagos-base/flagos-base-iluvatar-corex4.4.0:2.3.0 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```

*Last updated: 2026-10-14 13:43:56 · `393cfb81d50e`*

## Changelog

### 2.3.0

*2026-10-14 05:56:05*

- Rebuilt to carry the new stack-wide tag; nothing in this layer changed.

### 2.2.0

*2026-09-23 07:41:54*

- The CoreX CMake installer is given `--prefix`, the flag it honours; it had
  been passed `--target`, which it ignores, so from a cwd of `/` it unpacked
  into the root and `/opt/cmake-corex` — the directory `PATH` names — never
  existed. The build now asserts `cmake --version` rather than trusting the
  installer's exit status.

### 2.1.2

*2026-09-16 09:47:46*

- First delivery: Corex 4.4.0 with its CUDA header set and the vendor CMake
  3.31.8 on ubuntu:24.04.
- No `CPATH` is set: the corex clang already has `/usr/local/corex/include`
  on its default search path, while the CUDA 10.2 headers an earlier `CPATH`
  entry pointed at shadow corex's own `cuda.h` — runtime kernel compilation
  then aborts with `cuda.h did not define IX_VERSION`, and the operators
  that compile through Jiterator drop out.
