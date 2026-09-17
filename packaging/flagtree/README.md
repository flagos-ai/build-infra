<!--
 Copyright 2026 FlagOS Contributors

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 -->

# FlagTree wheel builders

Containerfiles that build **FlagTree wheels** for a backend from source, so the
wheel is self-owned and reproducible — and an A/B baseline against the vendor's.

The `nvidia-cuda` / `metax` / `sunrise` builders start from a plain Ubuntu 22.04
(old glibc: the resulting `libtriton.so` must load on 22.04 nodes) and pre-stage
the backend's prebuilt deps into FlagTree's offline cache. The `ascend3.5` /
`ascend3.2` pair instead builds **inside the backend's runtime image**, because
FlagTree's Ascend build needs CANN on the build machine — see the section below.

| File         | Target             | Base                        |
|--------------|--------------------|-----------------------------|
| `nvidia-cuda`| FlagTree for NVIDIA| Ubuntu 22.04 (glibc 2.35)   |
| `metax`      | FlagTree for MetaX (MACA) | Ubuntu 22.04 (glibc 2.35) |
| `sunrise`    | FlagTree for Sunrise (PTPU) | Ubuntu 22.04 + clang/lld 14 |
| `ascend3.5`  | FlagTree for Ascend, CANN 9.0.0 (aarch64 / cp311) | `flagos-runtime-ascend-cann9.0.0` |
| `ascend3.2`  | FlagTree for Ascend, CANN 8.5.0 (aarch64 / cp311) | `flagos-runtime-ascend-cann8.5.0` |

The `metax` builder exists because MetaX's own wheel (`flagtree==0.6.1+metax3.6`)
is built on Ubuntu 24.04 and links `libtriton.so` against `GLIBC_2.38` +
`GLIBCXX_3.4.32`, which do not exist on 22.04 — the client aborts before
`main()` with `version 'GLIBC_2.38' not found`. The MetaX LLVM and
`metaxTritonPlugin.so` are themselves clean, so a plain 22.04 rebuild is enough
(no symbol patching, no static libstdc++). It pre-stages the prebuilt MetaX deps
(LLVM, plugin, triton toolkits) into FlagTree's offline cache, and a post-build
**objdump gate fails the build** if any 22.04-incompatible symbol
(`GLIBC_2.38`, `GLIBCXX_3.4.31/32`, `__isoc23_*`) reappears in `libtriton.so`.

It also **pins pybind11** (`PYBIND11_SPEC`, default `>=3.0,<3.1`) because that is
an ABI contract, not just a dependency. The prebuilt `metaxTritonPlugin.so` is
compiled against pybind11 internals **v11**; `libtriton.so` and the plugin share
pybind11 type registries only when their internals versions match. FlagTree
requires only `pybind11>=2.13.1` (no upper bound), so an unpinned build pulls
pybind11 3.1.0 — which bumped the internals version to **v12** — and the wheel
imports fine but fails on real MetaX hardware at kernel-compile time with
`metax.load_dialects(ctx)` → `TypeError: incompatible function arguments`. The
CI smoke test (`import triton`) runs on a GPU-less box and cannot catch this, so
the gate additionally **asserts libtriton's pybind11 internals are v11**
(verified on metax124: v11 → `test_abs.py` 36/36 pass; v12 → 36/36 fail).

## Ascend builders (`ascend3.5` / `ascend3.2`)

The Ascend pair differs from the builders above in one structural way: **the build
environment is the backend's own runtime image**, not a plain Ubuntu.

FlagTree's Ascend build reads the CANN version *on the build machine* and uses it
to select the AscendNPU-IR branch/commit (`python/setup_tools/utils/ascend.py`,
`ASCEND_NPU_IR_PINS`); AscendNPU-IR is then compiled from source into the build
and the Ascend plugin links CANN's BiShengIR dialects. Building inside
`flagos-runtime-ascend-cann{9.0.0,8.5.0}` makes that pairing automatic — the pin
follows the CANN the wheel will actually run against — and the image is already a
complete toolchain for the build (python 3.11 venv with pip/ninja/pybind11,
gcc/make/cmake/binutils, git/curl/tar, torch + torch_npu), so no apt step is
needed. Same rule as the Megatron wheel builder: build env == delivery env.

| | `ascend3.5` | `ascend3.2` |
|---|---|---|
| Base image | `flagos-runtime-ascend-cann9.0.0:{version}` | `flagos-runtime-ascend-cann8.5.0:{version}` |
| FlagTree branch (default) | `0.7.0-rc2-triton3.5` (build dir = repo root) | `triton_v3.2.x` (build dir = `python/`) |
| Prebuilt LLVM | `llvm-7d5de303-…-compat_v0.6.0` | `llvm-a66376b0-…-compat_v0.3.0` |
| triton build deps | `build-deps-triton_3.5.x-linux-aarch64` | `build-deps-triton_3.2.x-linux-aarch64` |
| Wheel version | `0.7.0rc2+ascend3.5.<UTC date>` | `0.6.0+ascend3.2.<UTC date>` |

Notes that apply only here:

- **`PYTHONPATH` must be dropped during the build and the smoke test.** The
  runtime image's `/etc/profile.d/zz-compiler.sh` puts the *vendor* FlagTree
  (`/opt/flagtree`) on `PYTHONPATH` in every bash shell, so a naive
  `import triton` imports the vendor wheel and the smoke test would pass against
  something this build never produced. The source is cloned to
  `/opt/flagtree-src` (never `/opt/flagtree`), the build unsets `PYTHONPATH`, and
  the smoke installs into `/opt/wheel-test` with `PYTHONPATH` pointing there and
  asserts `triton.__file__` plus the distribution version.
- **pybind11 is pinned to the runtime image's own version** (`PYBIND11_SPEC`,
  default `==3.0.3` = internals v11, matching `configs.yaml runtime_prereqs`).
  Neither branch's `requirements.txt` has an upper bound, so an unpinned install
  pulls pybind11 3.1.x and silently moves the wheel to internals v12; the gate
  asserts v11.
- **The CANN version is a gate, not decoration**: `CANN_VERSION` is compared
  against the toolkit found in the image, so a wrong `BASE_IMAGE` fails the build
  instead of producing a wheel pinned to the wrong AscendNPU-IR.
- One wheel serves both 910B and 910C per CANN version: only the ops package
  differs between the chips, and the AscendNPU-IR pin depends on the toolkit
  version alone — matching the vendor, which ships a single `+ascend3.5` /
  `+ascend3.2` wheel.
- The wheel version is **ours**, not the vendor's release label: it says which
  FlagTree line the wheel came from, and the UTC date makes a rebuild
  distinguishable from the vendor's wheel of the same line.
- Not yet exercised: `upload=true` on a CANN node. The upload step uses the
  runner's own `python3`; if the aarch64 CANN runners have no pip, it needs the
  Megatron wheel workflow's approach (run twine inside the build image).
- The base image is the backend's **runtime** image at the stack version
  (`configs.yaml version:`), which a version bump reaches later than the base
  images — until it is published, `flagtree-wheel.yml`'s `base_image` input
  takes another tag of the same CANN line (e.g. `:2.2.0-build`) so the builder
  can still be validated. Blank = the derived runtime image, which is what a
  real build must use.
- Both builders share `verify_ascend_wheel.py` (the build gates) as a file
  COPYed into the build rather than a heredoc: the CANN nodes still run Docker's
  legacy builder, which has no heredoc support.
- The CANN version gate is what makes a base-image mistake loud: build against
  the wrong toolkit and the AscendNPU-IR pin follows it silently, so
  `CANN_VERSION` is compared against the toolkit actually present.

## Build

Run from inside this folder:

```sh
podman build -t flagtree-build:0.6.0 -f nvidia-cuda .

# behind a proxy:
podman build --build-arg http_proxy=$http_proxy --build-arg https_proxy=$https_proxy \
             -t flagtree-build:0.6.0 -f nvidia-cuda .

# ascend pair: aarch64 only, and the FROM image is the backend's runtime image
# (pulled from the registry if absent). The build itself clones github.com, so
# the proxy args matter here too; --build-arg no_proxy=... is relayed verbatim
# and never invented inside the Containerfile.
docker build -t flagtree-ascend3.5:0.7.0rc2 -f ascend3.5 .
```

Useful build args (see the Containerfile for the full list):

- `FLAGTREE_VERSION` — FlagTree git branch/tag/sha to build; also the wheel version
  string (default `0.6.0` for `nvidia-cuda`, `0.6.1+metax3.6` for `metax`). This
  is the single version knob.
- `FLAGTREE_WHEEL_VERSION` — wheel version string; defaults to `FLAGTREE_VERSION`,
  so you normally only set `FLAGTREE_VERSION`. A clean version (no `+git<sha>`)
  also needs `FLAGTREE_PYPI_KEY`; otherwise the wheel is versioned `<ver>.git<sha>`
  (the `metax` builder gets a clean version without the key by dropping `.git`).
  On the ascend pair it defaults to `FLAGTREE_BASE_VERSION.<UTC date>` instead
  (the ref and the wheel label are two separate knobs there).
- `FLAGTREE_PYPI_KEY` — unlocks the clean version (md5-gated in FlagTree's
  `setup.py`).

The build runs in `Release` mode, which strips `libtriton.so` (~840 MB → ~150 MB)
and drops asserts. A smoke test installs the freshly built wheel and imports
`triton`, failing the build if the wheel is broken.

## Extract the wheel

The wheel is written to `/wheels` in the image:

```sh
id=$(podman create flagtree-build:0.6.0)
podman cp $id:/wheels ./wheels
podman rm $id
```
