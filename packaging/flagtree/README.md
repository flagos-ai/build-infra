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
(old glibc: the resulting `libtriton.so` must load on 22.04 nodes). The
`ascend-cann9.0.0` / `ascend-cann8.5.0` pair instead builds **inside the
backend's runtime image**, because FlagTree's Ascend build needs CANN on the
build machine — see the section below. `iluvatar` is the odd one out: its
builder stage is a plain 22.04 like the first group, but the file carries a
**second stage** that installs CoreX on top and produces a flagtree image — see
below. `nvidia-cuda` also has two stages, for a different reason: see its own
section.

| File         | Target             | Base                        |
|--------------|--------------------|-----------------------------|
| `nvidia-cuda`| FlagTree for NVIDIA, builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `metax`      | FlagTree for MetaX (MACA) | Ubuntu 22.04 (glibc 2.35) |
| `sunrise`    | FlagTree for Sunrise (PTPU) | Ubuntu 22.04 + clang/lld 14 |
| `iluvatar`   | FlagTree for Iluvatar (CoreX), builder + image | Ubuntu 22.04 (glibc 2.35) + CoreX 4.5.0 |
| `ascend-cann9.0.0` | FlagTree for Ascend, CANN 9.0.0 (aarch64 / cp311) | `flagos-runtime-ascend-cann9.0.0` |
| `ascend-cann8.5.0` | FlagTree for Ascend, CANN 8.5.0 (aarch64 / cp311) | `flagos-runtime-ascend-cann8.5.0` |

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

## NVIDIA builder (`nvidia-cuda`)

`nvidia-cuda` is the only builder whose **build machine** is published, and it
has two stages for a reason the others do not have: nothing it stages up front
depends on the FlagTree ref being built.

```
ubuntu:22.04 ──> builder   apt toolchain + python 3.12 + prebuilt LLVM
                   │        published to flagos-dev by flagtree-builder-nvidia.yml
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

Removing `.git` is also what makes the version clean: FlagTree's
`get_git_commit_hash()` appends `+git<sha8>` whenever `git rev-parse` answers,
which is why the sha has to be read *before* the removal. Read it back with
`pip show -v`, not from the version.

## Iluvatar builder (`iluvatar`)

Same reason as `metax`: the vendor's own wheel is built on Ubuntu 24.04. Measured
on `flagos-pypi-hosted`'s `flagtree==0.7.0rc2+iluvatar3.6` (cp312):

| Object | max GLIBC | max GLIBCXX | `__isoc23_*` |
|---|---|---|---|
| `triton/_C/libtriton.so` | **2.38** | **3.4.32** | 1 |
| `triton/_C/iluvatarTritonPlugin.so` | 2.29 | 3.4.26 | 0 |

22.04 is glibc 2.35 / gcc 11.4 (GLIBCXX 3.4.30), so a 22.04 client aborts before
`main()`. Rebuilt here from the `0.7.0-rc2-triton3.6` branch, `libtriton.so` comes
out at **GLIBC 2.34 / GLIBCXX 3.4.30 / no `__isoc23_`**, which is what the gate
asserts. pybind11 is pinned to the vendor's internals **v12**
(`PYBIND11_SPEC=>=3.1,<3.2`), for the ABI reason described under `metax`.

**Two stages, one file.** `--target builder` is the publishable artifact, pushed
by `flagtree-builder.yml` to
`harbor.baai.ac.cn/flagos-dev/flagtree-builder-iluvatar-corex4.5.0:{version}`;
the default target is a flagtree image that takes that stage's venv and wheel.
The file is self-contained — `docker build -f iluvatar .` needs no script or
sibling file from this repo, which is what lets the published builder be the
whole recipe for reproducing the wheel. `iluvatar` is deliberately **not** a
`flagtree-wheel.yml` target: the wheel keeps the vendor's version string, so a
second workflow able to upload it would be a second uploader of one version.

**The plugin is linked in, not shipped.** The 3.6 branch builds
`triton_iluvatar.cc` as an object and links it into `libtriton.so`
(`add_triton_plugin` in `third_party/iluvatar/CMakeLists.txt`), so there is no
separate `iluvatarTritonPlugin.so` as the vendor wheel has. The gate therefore
asserts the plugin's symbol (`translateLLVMIRToILUVATAR`) is *in* `libtriton.so`
rather than asserting a second file. LLVM, the triton toolkits and a pinned
`FlagPrism` clone are staged into FlagTree's offline cache first, as the other
plain-22.04 builders do.

**The gate is a file, not a heredoc.** It was written `RUN python - <<'PY'`,
which on Docker's **legacy builder** — what the CoreX nodes run — never reaches
python's stdin: the step runs an empty program and exits 0. It printed nothing,
and a wheel missing an assertion target built "successfully". It now writes
itself to `/tmp/gate.py` with `printf` and runs that, which behaves the same on
both builders. Anything meant to fail a build has to be exercised on the builder
the job actually runs on.

**No `flag_gems`.** The image is the flagtree build platform — the shape of
`runtime:v1` (`NO_FLAGGEMS`), where a source build or a triton test runs — not a
runtime image. `flag_gems` depends on triton, so shipping it would also hide
whether the triton in the image works.

**CoreX's cmake installer takes only `--prefix=dir`** and unpacks into the
current directory for any other spelling. Here that is `/`, so the image stage
moves the modules from `/share` to `/usr/share` and asserts `cmake --version`.
The iluvatar bases carried the same defect; they now pass `--prefix` (#1011).

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
- **The proxy is applied per step, not per build.** Direct github access from the
  CANN nodes is not stable, so `flagtree-wheel.yml` relays it as `PROXY_URL` (never
  as `http_proxy`, which would be in the environment from the start) and the clone
  / build steps probe first, falling back only when the direct call fails. The
  prebuilt-deps download never uses it: the proxy answers HTTP 500 for that bucket
  while it is reachable directly.
- Both builders share `verify_ascend_wheel.py`, COPYed into the build rather than
  a heredoc: the CANN nodes still run Docker's legacy builder.
- Build cost on the CANN nodes: ~26 min for `ascend-cann9.0.0` and ~14 min for
  `ascend-cann8.5.0`, most of it compiling AscendNPU-IR and triton at `MAX_JOBS=32`.
  The github clone is the variable part — when it retries, the run is that much
  longer, whatever the proxy probe said.
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
             -t flagtree-build:0.7.0 -f nvidia-cuda .

# nvidia-cuda's build machine on its own, and then a wheel build on top of it:
docker build --target builder -t flagtree-builder-nvidia-cuda:ci -f nvidia-cuda .
docker build --build-arg BUILDER_IMAGE=flagtree-builder-nvidia-cuda:ci \
             -t flagtree-build:0.7.0 -f nvidia-cuda .

# ascend pair: aarch64 only, and the FROM image is the backend's runtime image
# (pulled from the registry if absent). The build itself clones github.com, so
# the proxy args matter here too; --build-arg no_proxy=... is relayed verbatim
# and never invented inside the Containerfile.
docker build -t flagtree-ascend-cann9.0.0:0.7.0rc2 -f ascend-cann9.0.0 .
```

Useful build args (see the Containerfile for the full list):

- `FLAGTREE_VERSION` — FlagTree git branch/tag/sha to build; also the wheel version
  string (default `0.7.0` for `nvidia-cuda`, `0.6.1+metax3.6` for `metax`). This
  is the single version knob.
- `FLAGTREE_WHEEL_VERSION` — wheel version string; defaults to `FLAGTREE_VERSION`,
  so you normally only set `FLAGTREE_VERSION`. Every builder here ends up with a
  clean version (no `+git<sha>`): `metax`/`sunrise`/`nvidia-cuda` and the ascend
  pair all drop `.git` before `pip wheel`, and `FLAGTREE_PYPI_KEY` (md5-gated in
  FlagTree's `setup.py`) is the other route for a caller that holds the secret.
  On the ascend pair it defaults to `FLAGTREE_BASE_VERSION.<UTC date>` instead
  (the ref and the wheel label are two separate knobs there).
- `FLAGTREE_WHEEL_NAME` — the distribution name FlagTree's `setup.py` publishes
  under. Default `flagtree`; the daily line sets `flagtree-nvidia` (see below).
- `FLAGTREE_PYPI_KEY` — unlocks the clean version (md5-gated in FlagTree's
  `setup.py`). Set by no caller in this repo.
- `BUILDER_IMAGE` — `nvidia-cuda` only. The image stage 1 builds on; defaults to
  `ubuntu:22.04` (the cold build). Pointing it at the published builder stage
  makes stage 1 a no-op — see the builder section above.

The build runs in `Release` mode, which strips `libtriton.so` (~840 MB → ~150 MB)
and drops asserts. A smoke test installs the freshly built wheel and imports
`triton`, failing the build if the wheel is broken. `nvidia-cuda` additionally
patches `python/flagtree/__init__.py` and records the source commit after the
clone (see below).

## Daily builds (`nvidia-cuda`)

`.github/workflows/flagtree-wheel-daily.yml` builds FlagTree `main` every day and
publishes it to `flagos-pypi-daily` under the distribution **`flagtree-nvidia`**.
The release line (`flagtree-wheel.yml`, manual) is untouched: it keeps
publishing plain `flagtree` to the vendor indexes.

The version is a date, and nothing else:

```
flagtree_nvidia-0.7.1.dev20261015-cp312-cp312-linux_x86_64.whl
^^^^^^^^^^^^^^^ ^^^^^^^^ ^^^^^^^^
distribution    release  .dev date
```

**Consumer command.** With the backend in the distribution name, pip does the
ranking:

```sh
pip install --pre flagtree-nvidia   # newest daily, always
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

Two knobs in the workflow's `env:`: `FLAGTREE_VERSION_BASE` (the release this
daily leads — move it when `configs.yaml` moves on) and `FLAGTREE_DIST_NAME`
(names the wheel). Adding a backend is a second job with its own pair.

**`resolve` skips a day that has already been published**, before the build
runner is occupied at all and with nothing for Nexus to reject. The version is
known without a build — it is the UTC date — so the probe is just the index
listing for today's filename. A same-day re-run is skipped; a new UTC day always
builds, even when `main` has not moved, because the wheel for a new date is a
new wheel. What it was built from is in its METADATA, not in its name.

That skip does not know which ref was asked for, which is worth stating plainly:
a manual dispatch overriding `flagtree_version` on a day the cron has already
published is skipped as well. To build another ref the same day, point
`flagtree-wheel.yml` at `nvidia-cuda` — or wait for the next UTC date.

**And it builds on the published builder stage** (see the NVIDIA builder section
above): the `builder_image` input takes an override, and blank means the ref
derived from `build-config.yml` + `configs.yaml`. `ubuntu:22.04` is the cold path
and the fallback for before the builder has been published.

**Caveat for consumers.** `flagtree` and `flagtree-nvidia` both install the
top-level `triton/` and `flagtree/` packages, and neither declares
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
