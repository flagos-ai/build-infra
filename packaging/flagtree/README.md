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

The `nvidia-cuda` / `metax` / `sunrise` / `iluvatar` builders start from a plain
Ubuntu 22.04 (old glibc: the resulting `libtriton.so` must load on 22.04 nodes).
The `ascend-cann9.0.0` / `ascend-cann8.5.0` pair instead builds **inside the
backend's runtime image**, because FlagTree's Ascend build needs CANN on the
build machine — see the section below.

| File         | Target             | Base                        |
|--------------|--------------------|-----------------------------|
| `nvidia-cuda`| FlagTree for NVIDIA, builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `metax`      | FlagTree for MetaX (MACA), builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `sunrise`    | FlagTree for Sunrise (PTPU) | Ubuntu 22.04 + clang/lld 14 |
| `iluvatar`   | FlagTree for Iluvatar (CoreX), builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `ascend-cann9.0.0` | FlagTree for Ascend, CANN 9.0.0 (aarch64 / cp311) | `flagos-runtime-ascend-cann9.0.0` |
| `ascend-cann8.5.0` | FlagTree for Ascend, CANN 8.5.0 (aarch64 / cp311) | `flagos-runtime-ascend-cann8.5.0` |

The `metax` builder was written because MetaX's own wheel
(`flagtree==0.6.1+metax3.6` on the host index) is built on Ubuntu 24.04 and links
`libtriton.so` against `GLIBC_2.38` + `GLIBCXX_3.4.32`, which do not exist on
22.04 — the client aborts before `main()` with `version 'GLIBC_2.38' not
found`. The MetaX LLVM and `metaxTritonPlugin.so` are themselves clean, so a
plain 22.04 rebuild is enough (no symbol patching, no static libstdc++).

The vendor's current wheel no longer has that problem — `0.7.0+metax3.6` peaks at
`GLIBC_2.34` — but it is still built with debug info: `libtriton.so` is 793.7 MB
with all eight `.debug_*` sections, against 218.6 MB for the Release build here,
which is the whole of the 425.2 MB vs 204.6 MB wheel difference. It also carries
no `Source-Commit`. So the two things this builder now buys are **size** and
**provenance**, and both are gated: a post-build **objdump gate fails the build**
if any 22.04-incompatible symbol (`GLIBC_2.38`, `GLIBCXX_3.4.31/32`,
`__isoc23_*`) reappears in `libtriton.so`, and the smoke test fails without the
`Source-Commit` carrier in the wheel metadata. It pre-stages the prebuilt MetaX
deps (LLVM, plugin, triton toolkits) into FlagTree's offline cache so the build
wires its own inputs instead of fetching them.

The file is split the way `nvidia-cuda` is: `--target builder` is the build
machine (apt toolchain, python 3.12, the three prebuilt inputs) and is published
by `flagtree-builder.yml` to the builder prefix, while the default target clones
the ref and compiles on top of it. Passing the published stage as
`BUILDER_IMAGE` turns the first half into a no-op through the marker guard, so a
warm build pays for the clone and the compile only.

It also **pins pybind11** (`PYBIND11_SPEC`, default `pybind11==3.0.1`) because that
is an ABI contract, not just a dependency. The prebuilt `metaxTritonPlugin.so` is
compiled against pybind11 internals **v11**; `libtriton.so` and the plugin share
pybind11 type registries only when their internals versions match. FlagTree
requires only `pybind11>=2.13.1` (no upper bound), so an unpinned build pulls
pybind11 3.1.0 — which bumped the internals version to **v12** — and the wheel
imports fine but fails on real MetaX hardware at kernel-compile time with
`metax.load_dialects(ctx)` → `TypeError: incompatible function arguments`. The
internals version alone is not enough either: 3.0.1 and 3.0.4 both report v11,
but 3.0.4 changed the internals constructor, which crashes the prebuilt bindings
in the pybind11 dispatcher. FlagTree's own `_PYBIND11_INTERNALS_TO_PIP` maps v11
to exactly `pybind11==3.0.1` on `main` and on the `0.7.0` tag (the wider
`>=3.0,<3.1` was the `0.6.1` line's), so this pin is the project's own rule, not
ours. The CI smoke test (`import triton`) runs on a GPU-less box and cannot catch
any of it, so the gate additionally **asserts libtriton's pybind11 internals are
v11** (verified on metax124: v11 → `test_abs.py` 36/36 pass; v12 → 36/36 fail).

## Builders

Some of these Containerfiles split their build environment into a `--target
builder` stage: everything that does not depend on the FlagTree ref being built
(apt toolchain, interpreter, prebuilt LLVM / plugin / triton toolkits, staged
into FlagTree's offline cache). `nvidia-cuda`, `metax` and `iluvatar` have one;
`sunrise` and the ascend pair are still single-stage.

`.github/workflows/flagtree-builder.yml` publishes all of them in one matrix —
one job per entry in `backends.yaml`, which is where a backend's build-line facts
live: its Containerfile, the image repository the stage is published under, the
runner labels, the disk budget, and which extra proof the stage needs.
`flagtree-wheel-daily.yml` reads the same file for its rows. Adding a backend is
one entry, not a new workflow and not a second job.

The stage is tagged with the stack version (`configs.yaml` `version:`), so it is
flat: a rebuild overwrites it. The wheel lines build on top of it.

## NVIDIA builder (`nvidia-cuda`)

`nvidia-cuda` splits its build environment from the ref the way `metax` does.
For this backend there is a second reason: it is also the row the daily builds,
so the split is what lets a daily run pay for the clone and the compile only.

```
ubuntu:22.04 ──> builder   apt toolchain + python 3.12 + prebuilt LLVM
                   │        published to flagos-dev by flagtree-builder.yml
                   ▼
                flagtree   clone the ref, compile triton, /wheels/*.whl
                           flagtree-wheel-daily.yml builds this on the published stage
```

**What the split removes.** A cold build spends its first minutes on `apt-get` +
deadsnakes python, then pulls the LLVM bundle — 1.23 GB, the flakiest network
step of the run — unpacks it, and only then reaches the clone. Built on the
published stage, none of that runs again: the layer is already in the base image
and the marker guard makes the instruction a no-op. On a day whose wheel is
already published there is nothing to build at all, and the run stops before
occupying the runner (see the skip below).

**It does not make the build fast.** The wall is compiling triton/MLIR against
that LLVM, not fetching it, and nothing here removes it. What the split buys is
that the apt/python/LLVM cost is paid when *it* changes rather than on every
build, and that a warm build's failure surface is the network clone and the
compiler.

**The LLVM comes from the filestore, not upstream.** The same tarball is mirrored
at `flagos-filestore/llvm/` (the route `iluvatar` already uses for its own
snapshot); `FILESTORE`, `LLVM_HASH` and the tarball and directory names derived
from it are one `ARG` block. FlagTree consumes it through **`LLVM_SYSPATH`** —
the documented knob for a pre-installed LLVM, which its own CI uses for the
thrive backend. This is *not* the offline-cache mechanism `metax` / `sunrise` /
`iluvatar` use: those stage into `~/.flagtree/<backend>/` and rely on a
`register_cache` hook in FlagTree's per-backend module, and the default (nvidia)
backend has no such hook. It follows that **`TRITON_OFFLINE_BUILD` must stay
unset here** — on this backend it demands eight CUDA toolkit directories that
nothing stages, plus an offline directory holding FlagPrism and flagcx, and the
build fails without them.

**Nothing validates `LLVM_SYSPATH`.** A staged tree is trusted and used silently,
so a tree of the wrong revision would surface — at best — as a cmake error deep
in triton. The builder stage therefore leaves the hash it staged at
`/opt/flagtree-build-env.llvm`, and the wheel build checks three things against
it before compiling anything: that a record exists at all (a base image without
one did not come from the builder stage), that `LLVM_SYSPATH` really holds an
LLVM install tree (which is what catches `LLVM_HASH` being bumped here without a
republish), and that the record equals the `cmake/llvm-hash.txt` of the source
just cloned. Bumping `LLVM_HASH` means republishing the builder; the pin has
moved twice in the last six months upstream, so this is a real gate rather than
decoration.

**The two ways to build.** `flagtree-wheel-daily.yml` passes the published stage
as `BUILDER_IMAGE`, and the stage's marker file (`/opt/flagtree-build-env.ready`,
written last) turns its own earlier work into a no-op. A `docker build` with no
`--build-arg BUILDER_IMAGE` (the `flagtree-wheel.yml` sequence, and every local
build) defaults to `ubuntu:22.04` and stages the environment from scratch — the
same image, just without the pre-staged layers. The daily's `builder_image` input
takes either spelling, so the cold path is available on the runner too, without
waiting for a republished builder.

**The source commit is recorded, not encoded.** After the clone, before `.git`
is removed, the build reads the commit with `git rev-parse --short=8` and writes
a `setup.cfg` into the clone carrying it as a `Project-URL`:

```ini
[metadata]
project_urls =
    Source-Commit = https://github.com/flagos-ai/flagtree/commit/87918b76
```

FlagTree ships no `setup.cfg` of its own — the build **fails** if one ever
appears, rather than silently overwriting it — and setuptools merges the file
into the `setup()` call on its own, so this reaches the wheel METADATA without
changing a line of FlagTree source. The alternatives were measured and rejected:
a hand-written `PKG-INFO` does not survive into METADATA, and appending to the
`egg_info` output does not either.

**FlagCX is built out, not in.** The build exports `USE_FLAGCX=OFF` to make sure that
the wheel carries no flagcx at all. The runtime installs the `flagcx` package and, once
FlagTree falls back to it (upstream
[#1393](https://github.com/flagos-ai/FlagTree/pull/1393)), uses that library over the
vendored copy. Until that merges the wheel carries no `flagcx_wrapper` either, so TLE
keeps distributed support off whether or not the package is installed.

Removing `.git` to make the version clean: FlagTree's `get_git_commit_hash()` appends
`+git<sha8>` whenever `git rev-parse` answers, which is why the SHA has to be read
*before* the removal. Read it back with `pip show -v`, not from the version.

## Iluvatar builder (`iluvatar`)

Same reason as `metax`: the vendor's own wheel is built on Ubuntu 24.04. Measured
on `flagos-pypi-hosted`'s `flagtree==0.7.0rc2+iluvatar3.6` (cp312):

| Object | max GLIBC | max GLIBCXX | `__isoc23_*` |
|---|---|---|---|
| `triton/_C/libtriton.so` | **2.38** | **3.4.32** | 1 |
| `triton/_C/iluvatarTritonPlugin.so` | 2.29 | 3.4.26 | 0 |

22.04 is glibc 2.35 / gcc 11.4 (GLIBCXX 3.4.30), so a 22.04 client aborts before
`main()`. Rebuilt here, `libtriton.so` comes out at **GLIBC 2.34 / GLIBCXX
3.4.30 / no `__isoc23_`**, which is what the gate asserts. pybind11 is pinned to
the vendor's internals **v12** (`PYBIND11_SPEC=>=3.1,<3.2`), for the ABI reason
described under `metax`.

**Two stages, one file.** `--target builder` is the build machine — apt
toolchain, python 3.12, the pre-staged iluvatar LLVM and triton toolkits — and is
what `flagtree-builder.yml` publishes to
`harbor.baai.ac.cn/flagos-dev/flagtree-builder-iluvatar-corex4.5.0:{version}`;
the default target is the wheel build on top of it. No stage of this file
installs CoreX: a plain 22.04 toolchain is what produces the wheel, and the
vendor SDK belongs to the runtime images.

**The wheel leaves this line.** The builder line publishes the stage and nothing
else: a wheel is a wheel line's deliverable, so one version never has two
uploaders. The upload path for this backend is `flagtree-wheel.yml` with
`target=iluvatar`, where `prepare` maps the target to the `iluvatar-corex4.5.0`
runtime row for its runner labels and vendor index while still passing no
`BASE_IMAGE`.

**The plugin is linked in, not shipped.** This backend builds `triton_iluvatar.cc`
as an object and links it into `libtriton.so` (`add_triton_plugin` in
`third_party/iluvatar/CMakeLists.txt`), so there is no separate
`iluvatarTritonPlugin.so` as the vendor wheel has. The gate therefore asserts the
plugin's symbol (`translateLLVMIRToILUVATAR`) is *in* `libtriton.so` rather than
asserting a second file.

**Only binary artifacts are pre-staged.** `iluvatar-llvm22` (which the backend's
`register_cache` hook wires up as `LLVM_SYSPATH`) and the triton toolkits (where
FlagPrism finds json) come off our own filestore. Third-party **source** trees —
FlagPrism here, flagcx elsewhere — are not staged at all: FlagTree's own resolver
clones them during the build, so there is nothing for this file to pin and
nothing to go stale when upstream moves. `TRITON_OFFLINE_BUILD=1` is the vendor's
own setting for this backend and is what makes setup.py reject a dependency whose
syspath is unset — the check that keeps the staging honest.

The tarballs are staged **under the names upstream asks for**, and that name is
the only coupling: the LLVM version moves with the ref — FlagTree declares it in
`python/setup_tools/utils/iluvatar.py` and its own cache check adopts whatever is
at `~/.flagtree/iluvatar/iluvatar-llvm22-x86_64` — so a version bump is a rename
here and a republish, with the definition and the usage in the same snippet.
Nothing asserts the tarball's bytes: what the artifact *is* follows from its
name, and an md5 here would only fail after the fact, on an artifact nobody
chose.

**The gate is a file, not a heredoc.** It was written `RUN python - <<'PY'`,
which on Docker's **legacy builder** — what the CoreX nodes run — never reaches
python's stdin: the step runs an empty program and exits 0. It printed nothing,
and a wheel missing an assertion target built "successfully". It now writes
itself to `/tmp/gate.py` with `printf` and runs that, which behaves the same on
both builders. Anything meant to fail a build has to be exercised on the builder
the job actually runs on.

**The commit rides in the metadata.** As for `metax`: `.git` is removed before
`pip wheel` so the version comes out clean, and the commit read just before that
is carried as a `Project-URL: Source-Commit` line (mechanism above).

## Ascend builders (`ascend-cann9.0.0` / `ascend-cann8.5.0`)

The Ascend pair differs from the builders above in one structural way: **the build
environment is the backend's own runtime image**, not a plain Ubuntu. It is also
named after that backend rather than the FlagTree line it builds, so the
Containerfile name, `flagtree-wheel.yml`'s `target` and `generate_matrix.py`'s
backend name are one string.

FlagTree's Ascend build reads the CANN version *on the build machine* and uses it
to select the AscendNPU-IR branch/commit (`python/setup_tools/utils/ascend.py`,
`ASCEND_NPU_IR_PINS`); AscendNPU-IR is then compiled from source into the build
and the Ascend plugin links CANN's BiShengIR dialects. Building inside
`flagos-runtime-ascend-cann{9.0.0,8.5.0}` makes that pairing automatic — the pin
follows the CANN the wheel will actually run against — and the image is already a
complete toolchain for the build (python 3.11 venv with pip/ninja/pybind11,
gcc/make/cmake/binutils, git/curl/tar, torch + torch_npu), so no apt step is
needed. Same rule as the Megatron wheel builder: build env == delivery env.

| | `ascend-cann9.0.0` | `ascend-cann8.5.0` |
|---|---|---|
| Base image | `flagos-runtime-ascend-cann9.0.0:{version}` | `flagos-runtime-ascend-cann8.5.0:{version}` |
| FlagTree branch (default) | `0.7.0-rc2-triton3.5` (build dir = repo root) | `triton_v3.2.x` (build dir = `python/`) |
| Prebuilt LLVM | `llvm-7d5de303-…-compat_v0.6.0` | `llvm-a66376b0-…-compat_v0.3.0` |
| triton build deps | `build-deps-triton_3.5.x-linux-aarch64` | `build-deps-triton_3.2.x-linux-aarch64` |
| Wheel version | `0.7.0rc2+ascend3.5.<UTC date>` | `0.6.0+ascend3.2.<UTC date>` |

The wheel's version label keeps the vendor's `+ascend3.5` / `+ascend3.2` spelling
— that is what the `configs.yaml` pins and the backend docs reference — while the
file is named after the backend.

Notes that apply only here:

- **`PYTHONPATH` must be dropped during the build and the smoke test.** The
  runtime image's `/etc/profile.d/zz-compiler.sh` puts the *vendor* FlagTree
  (`/opt/flagtree`) on `PYTHONPATH` in every bash shell, so a naive `import triton`
  imports the vendor wheel. The source is cloned to `/opt/flagtree-src` (never
  `/opt/flagtree`), and the smoke installs into `/opt/wheel-test` and asserts
  `triton.__file__` plus the distribution version.
- **Two build-time pins, two different contracts.** `PYBIND11_VERSION` (default
  `3.0.3` = internals v11, matching `configs.yaml` runtime_prereqs) is an ABI
  contract with the runtime: an unpinned install pulls 3.1.x (v12), which imports
  fine but breaks at kernel-compile time on hardware. `NANOBIND_VERSION` (default
  `2.4.0`) is a contract with the prebuilt LLVM instead — its
  `MLIRDetectPythonEnv.cmake` asks for 2.4, and nanobind 3.x rejects that request,
  failing the build in cmake. Both are named `_VERSION`, not the `_SPEC` of the
  older builders: ARG splits on the first `=`, so `ARG X==3.0.3` would hand pip
  `pybind11=3.0.3`.
- **The CANN version is a gate, not decoration**: `CANN_VERSION` is compared
  against the toolkit found in the image, so a wrong `BASE_IMAGE` fails the build
  instead of producing a wheel built against the wrong CANN. The gate reads the
  install-info file the image actually ships — flagtree reads only
  `ascend_toolkit_install.info`, which CANN 9.0.0 does not ship, so the 3.5 build
  logs `CANN version not detected` and takes its default pin (the cann9.0.0 line,
  correct for this image, and the gate is what proves it).
- **The prebuilt LLVM bundles are newer than the source they compile.** Each
  builder carries a `TRITON_APPEND_CMAKE_ARGS` workaround for a hard error that
  comes from the bundle rather than from flagtree: 3.2's clang 21 fires
  `-Wdangling-assignment-gsl` on the bundle's own MLIR headers, and 3.5's FlagPrism
  does not compile without `<cstdint>`. See the Containerfiles for the specifics.
- One wheel serves both 910B and 910C per CANN version: only the ops package
  differs between the chips, and the AscendNPU-IR pin depends on the toolkit
  version alone — matching the vendor, which ships a single `+ascend3.5` /
  `+ascend3.2` wheel.
- The wheel version is **ours**, not the vendor's release label: it says which
  FlagTree line the wheel came from, and the UTC date makes a rebuild
  distinguishable from the vendor's wheel of the same line.
- The base image is the runtime image at the stack version (`configs.yaml
  version:`), which a version bump reaches later than the base images. Until it is
  published, `flagtree-wheel.yml`'s `base_image` input takes another tag of the
  same CANN line (e.g. `:2.2.0-build`). Blank = the derived runtime image, which is
  what a real build must use.
- **The proxy is the runner's, like every other builder.** The targets declare
  `http_proxy` / `https_proxy` / `no_proxy` and `flagtree-wheel.yml` relays all
  three verbatim; git, curl and pip read them on their own, and nothing in the
  build probes reachability or decides for the runner which endpoints are direct.
  A host a build must reach directly is therefore named in the runner's
  `no_proxy`, not in this tree.
- Both builders share `verify_ascend_wheel.py`, COPYed into the build rather than
  a heredoc: the CANN nodes still run Docker's legacy builder.
- Build cost on the CANN nodes: ~26 min for `ascend-cann9.0.0` and ~14 min for
  `ascend-cann8.5.0`, most of it compiling AscendNPU-IR and triton at `MAX_JOBS=32`.
  The github clone is the variable part — when it retries, the run is that much
  longer, whatever the egress was doing.
- `upload=true` works from the CANN nodes (exercised 2026-09-17: both wheels are in
  `flagos-pypi-ascend`, beside the vendor's). Those runners run pip 22.0.2, which
  has no `--break-system-packages`, so the plain `pip install --upgrade twine
  pkginfo` fallback is the branch that actually runs there.

## Build

Run from inside this folder:

```sh
podman build -t flagtree-build:0.7.0 -f nvidia-cuda .

# behind a proxy:
podman build --build-arg http_proxy=$http_proxy --build-arg https_proxy=$https_proxy \
             --build-arg no_proxy=$no_proxy \
             -t flagtree-build:0.7.0 -f nvidia-cuda .

# nvidia-cuda's build machine on its own, and then a wheel build on top of it:
docker build --target builder -t flagtree-builder-nvidia-cuda:ci -f nvidia-cuda .
docker build --build-arg BUILDER_IMAGE=flagtree-builder-nvidia-cuda:ci \
             -t flagtree-build:0.7.0 -f nvidia-cuda .

# ascend pair: aarch64 only, and the FROM image is the backend's runtime image
# (pulled from the registry if absent). The build clones github.com and fetches
# prebuilt deps, so the same three proxy args apply.
docker build -t flagtree-ascend-cann9.0.0:0.7.0rc2 -f ascend-cann9.0.0 .
```

Useful build args (see the Containerfile for the full list):

- `FLAGTREE_VERSION` — FlagTree git branch/tag/sha to build; also the wheel version
  string (default `0.7.0` for `nvidia-cuda`, `0.7.0+metax3.6` for `metax`,
  `0.7.1a1+iluvatar3.6` for `iluvatar`). This
  is the single version knob, and each default is the release the stack pins in
  `configs.yaml`: the wheel's version is what a client's `pip` ends up with, so
  the two are meant to agree.
- `FLAGTREE_WHEEL_VERSION` — wheel version string; defaults to `FLAGTREE_VERSION`,
  so you normally only set `FLAGTREE_VERSION`. Every builder here ends up with a
  clean version (no `+git<sha>`): `metax`/`sunrise`/`iluvatar`/`nvidia-cuda` and
  the ascend pair all drop `.git` before `pip wheel`, and `FLAGTREE_PYPI_KEY`
  (md5-gated in FlagTree's `setup.py`) is the other route for a caller that holds
  the secret.
  On the ascend pair it defaults to `FLAGTREE_BASE_VERSION.<UTC date>` instead
  (the ref and the wheel label are two separate knobs there).
- `FLAGTREE_WHEEL_NAME` — the distribution name FlagTree's `setup.py` publishes
  under. Default `flagtree`; the daily line sets `flagtree-nvidia` (see below).
- `FLAGTREE_PYPI_KEY` — unlocks the clean version (md5-gated in FlagTree's
  `setup.py`). Set by no caller in this repo.
- `BUILDER_IMAGE` — the staged builders (`nvidia-cuda`, `metax`, `iluvatar`). The
  image stage 1 builds on; defaults to `ubuntu:22.04` (the cold build). Pointing
  it at the published builder stage makes stage 1 a no-op — see the builder
  sections above.

The build runs in `Release` mode, which strips `libtriton.so` (~840 MB → ~150 MB)
and drops asserts. A smoke test installs the freshly built wheel and imports
`triton`, failing the build if the wheel is broken. `nvidia-cuda` additionally
patches `python/flagtree/__init__.py` and records the source commit after the
clone (see below).

## Daily builds

`.github/workflows/flagtree-wheel-daily.yml` builds FlagTree `main` every day and
publishes it to `flagos-pypi-daily`, one distribution per backend that has an
enabled `daily:` row — `flagtree-nvidia` and `flagtree-metax` today. The release
line (`flagtree-wheel.yml`, manual) is untouched: it keeps publishing plain
`flagtree` to the vendor indexes.

The version is a date, and nothing else:

```
flagtree_nvidia-0.7.1.dev20261015-cp312-cp312-linux_x86_64.whl
^^^^^^^^^^^^^^^ ^^^^^^^^ ^^^^^^^^
distribution    release  .dev date
```

**Consumer command.** With the backend in the distribution name, pip does the
ranking:

```sh
pip install --pre flagtree-nvidia   # newest nvidia daily, always
pip install --pre flagtree-metax    # newest metax daily, always
pip install flagtree-nvidia         # same thing today: no stable version of this name exists
pip uninstall flagtree-nvidia       # before switching back to the release name
```

`--pre` is the safe form — without it pip accepts pre-releases only while no
stable version of the name exists. Nothing under `flagtree-nvidia` is stable, so
both spellings resolve to the newest daily; a stable release of that name, if
one is ever published, would flip the no-`--pre` form over to it. What a plain
`pip install flagtree` gets is unaffected either way: dailies live under a
different name.

**Which commit is this?** Not from the version — from the wheel's metadata:

```sh
pip show -v flagtree-nvidia | grep Source-Commit
# Project-URL: Source-Commit, https://github.com/flagos-ai/flagtree/commit/87918b76

python -c "import importlib.metadata as m; \
           print(m.metadata('flagtree-nvidia').get_all('Project-URL'))"
```

Why the pieces sit where they do:

- **The date goes in the public segment, as `.dev`.** That is the only placement
  that is both a pre-release (so a plain `pip install flagtree` keeps resolving
  to the release) and numerically *above* the release it leads, so "newest
  daily" is version comparison rather than date-eyeballing. A dated release
  segment (`0.7.0.20261015`) is not a pre-release and would be picked by a plain
  `pip install flagtree`, shadowing the release; `0.7.0.dev<date>` sorts *below*
  `0.7.0`.
- **Nothing else is in the version.** The backend is the distribution name, and
  a backend token in the local segment cannot be matched anyway: a `==`
  specifier carrying a local label matches that whole segment exactly, and `dev`
  inside a local label compares as text — measured: `==0.7.1+nvidia3.6` matches
  neither `0.7.1+nvidia3.6.dev20261015` nor `0.7.1.dev20261015+nvidia3.6`, and
  `==0.7.1.*+nvidia3.6` is not even a valid specifier. With each backend its own
  project, `+nvidia3.6` repeats what the name already says.
- **The commit is metadata, not a filename.** FlagTree appends `+git<sha8>` to
  whatever version it is handed, so the only way to a date-only version is the
  `metax`/`sunrise`/`ascend` route: drop `.git` before `pip wheel`. The sha is
  read from `.git` first and written into the clone's `setup.cfg`, which
  setuptools merges into `setup()` on its own — that is what puts
  `Project-URL: Source-Commit, …` in the METADATA, with no line of FlagTree
  source changed (see the NVIDIA build section above).

Two knobs per backend, both in `packaging/flagtree/backends.yaml`'s `daily:`
block: `version_base` (the release this daily leads — move it when `configs.yaml`
moves on) and `dist_name` (names the wheel). `ref` is the FlagTree line that row
tracks — upstream's `main` for `nvidia` and `metax`, declared rather than taken
from the Containerfile's own default, which is the vendor release a local build
reproduces.

**The cron skips a day that has already been published; a manual run never
does.** The version is known without a build — it is the UTC date — so the plan
job probes that row's index listing for today's filename and drops the row
before any build runner is occupied, with nothing for Nexus to reject. A
same-day cron re-run is skipped; a new UTC day always builds, even when the ref
has not moved, because the wheel for a new date is a new wheel. What it was
built from is in its METADATA, not in its name. The decision is per row, so a
backend already published today neither occupies its runner nor holds up another
backend.

The manual dispatch is the escape hatch for a fix merged after 01:37, so skipping
it would defeat the only reason it exists. It publishes the same version the cron
did, and the upload replaces the file — Nexus on this server has redeploy
enabled, so a duplicate is a replacement rather than a 400. A second manual run
that day replaces the first the same way. One consequence to know about rather
than discover: a consumer holding the already-fetched wheel in a warm pip cache
keeps it, since neither the version nor the URL changed.

**And it builds on the published builder stage** (see the NVIDIA builder section
above): the `builder_image` input takes an override, and blank means the ref
derived from `build-config.yml` + `configs.yaml`. `ubuntu:22.04` is the cold path
and the fallback for before the builder has been published.

**Caveat for consumers.** `flagtree`, `flagtree-nvidia` and `flagtree-metax` all
install the top-level `triton/` and `flagtree/` packages, and none declares
`Obsoletes`/`Provides`, so pip treats them as unrelated projects and installing
one over the other clobbers files rather than replacing. Uninstall the old name
first.

### `print(flagtree.__version__)`

Upstream's `python/flagtree/__init__.py` is `from triton import __version__`, so
it reports the Triton line the build forked (`3.6.0`) and never the wheel's own
version. `packaging/flagtree/patch-flagtree-version.py` rewrites it — inside the
build, after the clone and before `pip wheel`, with a grep gate so the build
fails loudly if upstream's module moves on — to read
`importlib.metadata.version("flagtree-nvidia")`, falling back to the Triton line
when the distribution is not installed. The fork is not modified.

The source commit is deliberately not added a second time here: it lives in
`Project-URL: Source-Commit` in the same dist-info the module already reads its
version from, so one lookup answers both "which FlagTree" and "which commit".

## Extract the wheel

The wheel is written to `/wheels` in the image:

```sh
id=$(podman create flagtree-build:0.7.0)
podman cp $id:/wheels ./wheels
podman rm $id
```
