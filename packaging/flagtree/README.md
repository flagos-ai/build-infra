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

The `nvidia-cuda` / `metax` / `sunrise` / `iluvatar` / `enflame` / `tsingmicro`
builders start from a plain Ubuntu 22.04 (old glibc: the resulting
`libtriton.so` must load on 22.04 nodes).
The `ascend-cann9.0.0` / `ascend-cann8.5.0` pair's builder stage instead starts
from **the backend's runtime image**, because FlagTree's Ascend build needs CANN
on the build machine — see the section below.

| File         | Target             | Base                        |
|--------------|--------------------|-----------------------------|
| `nvidia-cuda`| FlagTree for NVIDIA, builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `metax`      | FlagTree for MetaX (MACA), builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `sunrise`    | FlagTree for Sunrise (PTPU), builder + wheel | Ubuntu 22.04 + clang/lld 14 |
| `iluvatar`   | FlagTree for Iluvatar (CoreX), builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `enflame`    | FlagTree for Enflame (GCU), builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `hcu`        | FlagTree for Hygon (DTK), builder + wheel | Ubuntu 22.04 (glibc 2.35) |
| `tsingmicro` | FlagTree for Tsingmicro (TX8), builder + wheel | Ubuntu 22.04 + staged clang 22 |
| `ascend-cann9.0.0` | FlagTree for Ascend, CANN 9.0.0 (aarch64 / cp311), builder + wheel | `flagos-runtime-ascend-cann9.0.0` |
| `ascend-cann8.5.0` | FlagTree for Ascend, CANN 8.5.0 (aarch64 / cp311), builder + wheel | `flagos-runtime-ascend-cann8.5.0` |

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
internals version alone is not enough either: 3.0.1, 3.0.3 and 3.0.4 all declare
v11, but 3.0.4 changed the internals constructor, which crashes the prebuilt
bindings in the pybind11 dispatcher. That last fact is upstream's, recorded in
**`xpu.py`**'s `_PYBIND11_INTERNALS_TO_PIP` (`11: pybind11==3.0.1`) — a table
about xpu's own prebuilt SDNN objects, not about metax: `metax.py` has no
pybind11 table at all, so the exact release here is read off *our* measurement of
the plugin (v11) plus that constructor note. The CI smoke test (`import triton`)
runs on a GPU-less box and cannot catch any of it, so the gate additionally
**compares libtriton's pybind11 internals against the plugin's** (verified on
metax124: v11 → `test_abs.py` 36/36 pass; v12 → 36/36 fail).

Both the pin and the gate live in the wheel stage, not the builder: a child
stage inherits a parent's `ARG` under BuildKit but not under Docker's legacy
builder, so an arg declared only above is empty on the runners that use the
latter. The gate compares rather than asserting a literal — the plugin is the
contract, and reading it back means the pin and the gate cannot drift apart.

## Builders

Some of these Containerfiles split their build environment into a `--target
builder` stage: everything that does not depend on the FlagTree ref being built
(apt toolchain, interpreter, prebuilt LLVM / plugin / triton toolkits, staged
into FlagTree's offline cache). All nine have one. For `nvidia-cuda`, `metax`,
`sunrise`, `iluvatar`, `enflame`, `hcu` and `tsingmicro` the stage starts from a
bare `ubuntu:22.04`
and is the `BUILDER_IMAGE` default; for the ascend pair its cold value is the
backend's runtime image, which is why `backends.yaml` marks those rows
`base_image: runtime` and the builder line resolves their `BUILDER_IMAGE` from
`generate_matrix.py --runtime` instead of letting the Containerfile default.

`.github/workflows/flagtree-builder.yml` publishes all of them in one matrix —
one job per entry in `backends.yaml`, which is where a backend's build-line facts
live: its Containerfile, the image repository the stage is published under, the
runner labels, the disk budget, and which extra proof the stage needs. That proof
is either a `verify_stage` name — a step in the workflow, for a stage whose
contract a path list cannot express (the ascend pair asserts the runtime image's
CANN line and version, its staged LLVM and the triton deps; the other four assert
a prebuilt plugin's md5 prefix or a symbol) — or a `verify` block, which is the
same assertions as data: the interpreter, the executables, the paths. The block
is rendered by one generic step, so a backend staged like its predecessors needs
a row and no workflow step at all. `enflame`, `hcu` and `tsingmicro` are the
three of those, and the four that came before them keep their own steps.
`flagtree-wheel-daily.yml` reads the same file for its rows. Adding a backend is
one entry, not a new workflow and not a second job.

The stage is tagged with the stack version (`configs.yaml` `version:`), so it is
flat: a rebuild overwrites it. The wheel lines build on top of it.

## Enflame builder (`enflame`)

Same reason and shape as `metax`: the vendor's enflame wheel is built on a newer
distro and drags symbols a 22.04 client cannot load, so this stage is a bare
`ubuntu:22.04` with a deadsnakes python 3.12 and the prebuilt inputs staged into
FlagTree's offline cache.

**The vendor toolkit deb is one of those inputs, and it is not optional.** This
backend's `third_party/enflame/backend/toolkit.py` raises *at import* when
`/opt/triton_gcu` is absent —

```python
datadir = os.getenv("TRITON_GCU_PATH") or "/opt/triton_gcu"
if not os.path.exists(datadir):
    raise Exception("Cannot find data directory in " + datadir)
```

— and `backend.py` imports it, so any client that imports the enflame backend
needs that directory. It is created by the vendor's `triton-gcu` deb
(`./opt/triton_gcu/**`, 3.3 GB unpacked), which `base/enflame-*` installs — so
the runtime images have it and a bare build machine does not. That is the whole
difference between a wheel that imports in the field and one that does not, so
the builder stage stages the deb the same way it stages LLVM and unpacks it with
`dpkg-deb -x … /`. The wheel stage's smoke test then imports the backend for
real: with the deb absent, `toolkit.py` raises there, where before it raised in
a user's process.

The deb is per-`tops` (`…cc.1.10.6` vs `…cc.1.9.10`) while one Containerfile
serves both, so `TRITON_GCU_DEB` (and `FILE_STORE`, the store the base image
reads) default to the deb `base/enflame-tops1.10.6` itself installs and a 1.9.10
build overrides both. Enflame is the only backend here whose vendor module raises
at import time — metax, iluvatar, sunrise, hcu, mthreads, tsingmicro and xpu all
raise inside functions — which is why this staging is a hard requirement rather
than a convenience.

**No pybind11 pin and no plugin tarball.** `enflame.py` ships no
`register_cache` pybind11 table and no prebuilt `.so` is an ABI counterparty —
every binding in this wheel is compiled here from one pybind11 — so there is
nothing for a pin to agree with. The gate asserts what enflame.py does declare:
the GCU tools, both core libraries and both python bindings, by basename.

**Two settings that are the vendor's.** `TRITON_APPEND_CMAKE_ARGS=-DCMAKE_BUILD_TYPE=Release`
and the `Source-Commit` carrier in `setup.cfg`, which is the same
`.git`-before-`pip wheel` route `metax` takes to a clean date version.

## Hygon builder (`hcu`)

The same shape as `enflame` — bare `ubuntu:22.04`, apt toolchain, the backend's
prebuilt LLVM and the shared triton toolkits into FlagTree's offline cache — with
two differences.

**It is the system python 3.10, not a deadsnakes 3.12.** `configs.yaml` pins
`hygon-dtk26.04` at python 3.10, so the wheel has to wear `cp310`; 22.04 ships
that interpreter, so there is no PPA to wire by hand.

**No vendor SDK, no clang, no apt LLD.** `hcu.py`'s `install_extension` is a
no-op and `third_party/hcu/backend/include/hip/**` is tracked in git, so nothing
outside the staged LLVM is needed to compile — and hcu is on cmake's gcc flag
list, not the clang one. LLD is a `find_package(LLD REQUIRED CONFIG)` in
`third_party/hcu/CMakeLists.txt`, resolved against `LLD_DIR`, which CMakeLists
defaults to `${LLVM_LIBRARY_DIR}/cmake/lld`; the staged LLVM ships that file
along with `liblldCommon.a`/`liblldELF.a`, so no `lld-14` package is staged. The
same tree supplies `bin/FileCheck`, which CMakeLists copies into the wheel.

**Two settings that must stay unset.** `hcu.py`'s one `register_cache` entry
short-circuits on `LLVM_SYSPATH` (`pre_hook=check_env(...)`), so exporting it
sends the build to the vendor's ks3 bucket instead of the staged tree; and
`TRITON_OFFLINE_BUILD` makes `get_thirdparty_packages` raise unless
`JSON_SYSPATH` is set too. Staging the cache without either variable is what
lets FlagTree's own hook run and export the paths.

**No pybind11 pin.** As with enflame, no prebuilt `.so` is an ABI counterparty,
so the gate has nothing to read a pin off. It asserts the invariant instead:
`libtriton.so` and every other tagged `.so` in `triton/_C` carry the same
pybind11 internals version as the `pybind11` the build installed.

**Verified on a BW1000 node** (hygon25, 2026-10-20). The wheel built on the
published builder imports on the `flagos-runtime-hygon-dtk26.04` image and runs
a real kernel: `import triton` reports triton 3.6.0 with `backends == ['hcu']`,
the driver resolves `GPUTarget(backend='hip', arch='gfx936', warp_size=64)`, and
a vector-add kernel returns `max diff 0.0` against torch's own result. No DTK is
needed at import time — `HIPUtils.__init__` is reached lazily on the first launch,
and the image supplies it there.

## Tsingmicro builder (`tsingmicro`)

The same shape as `hcu` — bare `ubuntu:22.04`, apt toolchain, the backend's
prebuilt inputs into FlagTree's offline cache — with these differences.

**It is the system python 3.10, not a deadsnakes 3.12.** `configs.yaml` pins
`tsingmicro-tsm260610` at python 3.10, so the wheel has to wear `cp310`; 22.04
ships that interpreter, so there is no PPA to wire by hand.

**Two prebuilt trees, not one.** `tsingmicro.py` registers two caches,
`tsingmicro-llvm22` and `tx8_deps`, and both are staged: the first is the LLVM the
backend compiles with, the second is the vendor's `TX8_DEPS_ROOT` (the Xuantie
RISC-V toolchain the crt links its runtime with, the profiling library
`driver.py` hard-links at import, and `rcsfw_include_interface.cmake`, which
`third_party/tsingmicro/CMakeLists.txt` `include()`s). FlagTree matches a cache
by directory name, so each tarball is unpacked with `--strip-components=1` onto
the exact key — the vendor's own roots are `tsingmicro-llvm22/` and `tx8_deps/`,
but relying on that would break the day either tarball is repacked.

**The staged clang has to reach cmake through PATH.** `FlagTreeOptions.cmake`
selects `clang`/`clang++` for this backend by bare name, with no PATH
manipulation of its own (unlike `mthreads`), so no apt clang is installed at all
and the staged `bin` is prepended in the wheel stage. The crt and the profiler
are compiled with an absolute `${LLVM_SYSPATH}/bin/clang` through the same
variable, so both stages end up on one compiler.

**No import smoke test.** The other builders install their wheel and import it.
This one cannot: `third_party/tsingmicro/backend/driver.py` imports `torch_txda`
at module level, `import triton` reaches it through backend discovery, and
`torch_txda` aborts unless the TX8 device nodes are present — a docker build can
never be handed `/dev/accel`. The build instead asserts what it can: that the
wheel installs, and that `tsingmicro-opt`, `tx-profiler` and `libvr.a` are in it
at a plausible size. That assertion is not decoration —
`install_extension` prints a warning and *continues* when the CMake build tree did
not produce one, so a wheel missing `tsingmicro-opt` (482 MB) would otherwise be
built, gated and published. The import itself is verified on the backend's own
node, with the devices attached.

**Two settings that must stay unset.** Same as `hcu`, and for the same reason:
each of `tsingmicro.py`'s two cache entries short-circuits on the variable its
post-hook would export (`LLVM_SYSPATH`, `TX8_DEPS_ROOT`), so exporting either
sends the build to the vendor's ks3 bucket instead of the staged tree.

**Verified on a TX8110 node** (tsm-249, 2026-10-21). The wheel built on the
published builder imports on the `flagos-runtime-tsingmicro-tsm260610` image and
runs a real kernel: `import triton` reports triton 3.6.0 with
`backends == ['tsingmicro']`, the driver resolves
`GPUTarget(backend='txda', arch=1, warp_size=16)`, and a vector-add kernel
returns `max diff 0.0` against torch's own result. The runtime image already
carries the vendor's flagtree at `/opt/flagtree` on `PYTHONPATH`, so the check
installs the wheel to its own directory and prepends it — a bare `import triton`
would resolve to the vendor tree and prove nothing. The container needs
`--device /dev/accel --device /dev/accel_drv_mgr`; without them `torch_txda`
aborts at import, which is the same reason the build stage has no smoke test.

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
internals **v12** (`PYBIND11_SPEC=>=3.1,<3.2`, resolving to 3.1.0) because this
wheel replaces the vendor's and must stay on the ABI the vendor's other objects
carry — the vendor wheel's `libtriton.so`, `flagtree/debugger/_native` and
`flagtree/profiler/_native` all embed v12. Unlike `metax` and `sunrise` there is
no prebuilt `.so` in *this* build to compare against (the plugin is compiled from
source in the same pass, and neither the staged LLVM nor the triton toolkits
carry a pybind11 tag), so the gate reads `PYBIND11_INTERNALS_VERSION` out of the
*installed* pybind11 and compares — the pattern `verify_ascend_wheel.py` uses.

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
`BUILDER_IMAGE` — this stage cold-builds from bare `ubuntu:22.04`.

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

## Sunrise builder (`sunrise`)

Same reason as `metax` and `iluvatar`: the vendor's sunrise wheel is built on
Ubuntu 24.04 and drags `GLIBC_2.38` + `GLIBCXX_3.4.32` into `libtriton.so`, which
a 22.04 client cannot load. It is also the only builder here whose interpreter is
the base's own python 3.10 — sunrise builds against clang/lld 14 and ships a
`cp310` wheel — so its gate and smoke test are written for `python3.10`.

**clang/lld is a correctness requirement, not a preference.** Upstream builds
this backend with `TRITON_BUILD_WITH_CLANG_LLD=1` and it is load-bearing:
`cmake/FlagTreeOptions.cmake` lists the gluon-compiling backends for
`-Werror -Wno-attributes -Wno-comment -Wno-error=odr` but omits sunrise, which
falls into the else-branch `-Werror -Wno-covered-switch-default` — a clang-only
option. Under gcc-11 that option is unrecognized, so `-Werror` is fully armed and
`gluon_ir.cc`'s `GluonLayouts` (pybind11 `handle` fields of hidden visibility)
fails with `-Werror=attributes`. Upstream never sees it because its own sunrise
recipes always build with clang, which is also why this file stages clang/lld 14
with the unversioned symlinks `setup.py` and `-fuse-ld=lld` look for.

**Two stages, one file**, the `metax` shape: `--target builder` is the build
machine (apt toolchain, python 3.10, the prebuilt sunrise LLVM + plugin + triton
toolkits) and is what `flagtree-builder.yml` publishes to
`harbor.baai.ac.cn/flagos-dev/flagtree-builder-sunrise:{version}`; the default
target clones the ref and compiles on top of it.

**Three prebuilt inputs, staged by the names upstream asks for.** Unlike
`nvidia-cuda`, this backend has a `register_cache` hook
(`python/setup_tools/utils/sunrise.py`) that resolves its inputs out of
`~/.flagtree/sunrise/` — so the stage unpacks the LLVM and plugin tarballs there
under the cache keys `sunrise_llvm22_dev_release` / `sunriseTritonPlugin.so`, and
the triton toolkits into `~/.triton`. The plugin `.so` is md5-gated to
`4c77b8c0`, the digest upstream itself declares; the LLVM tarball is not, for the
reason `iluvatar`'s is not.

**The LLVM tree is a full clang install.** `sunrise_llvm22_dev_release` carries
`bin/clang` **and** `lib/cmake/mlir`, and its `stpu/bitcode/*.bc` is what the
cache's `post_hook` copies into `third_party/sunrise/backend/lib` — all three are
asserted by the builder line's `sunrise` stage check, because a stage missing any
of them builds a different wheel rather than failing.

**pybind11 is pinned to `==3.1.0`, not to a range.** The prebuilt
`sunriseTritonPlugin_v0.6.0.4.so` embeds pybind11 internals **v12**, and
upstream's `sunrise.py` maps v12 to exactly `pybind11==3.1.0` — its
`check_pybind11_abi()` compares the patch release, not just the internals
version, for the same reason `xpu.py` does. That table is on `main`; the ref this
file builds (`0.7.0+sunrise3.6`) predates the hook — its `sunrise.py` has only
`register_cache` — so the value reaches this build from upstream's rule while the
enforcement is ours: the gate reads the internals out of both the prebuilt plugin
and the freshly built `libtriton.so` and fails if they differ. Same v12 as
`iluvatar`, opposite of `metax`, whose plugin is v11.

**The wheel ships the `tang` alias.** Upstream renamed `triton.language.extra.tang`
to `ptpu`; `flag_gems <=5.3.4` still imports the old spelling, so the build
symlinks `ptpu -> tang` inside the backend's `language/` tree and the gate asserts
both directories are in the wheel.

**Two settings that are the vendor's, not ours.** `TRITON_BUILD_PROTON=OFF` (the
backend has no profiler) and `TRITON_OFFLINE_BUILD=1`, which makes `setup.py`
abort on a third-party package whose `*_SYSPATH` is unset — the check that keeps
the staging honest. What is staged for `~/.triton` is the triton-deps tarball,
rooted at `.triton/` and therefore unpacked with `--strip-components=1`.

## Ascend builders (`ascend-cann9.0.0` / `ascend-cann8.5.0`)

The Ascend pair differs from the builders above in one structural way: **its
builder stage's cold base is the backend's own runtime image**, not a plain
Ubuntu — so its `BUILDER_IMAGE` default is a registry ref rather than
`ubuntu:22.04`, and a cold build pulls that image. The pair is also named after
the backend rather than the FlagTree line it builds, so the Containerfile name,
`flagtree-wheel.yml`'s `target` and `generate_matrix.py`'s backend name are one
string.

FlagTree's Ascend build reads the CANN version *on the build machine* and uses it
to select the AscendNPU-IR branch/commit (`python/setup_tools/utils/ascend.py`,
`ASCEND_NPU_IR_PINS`); AscendNPU-IR is then compiled from source into the build
and the Ascend plugin links CANN's BiShengIR dialects. Building on
`flagos-runtime-ascend-cann{9.0.0,8.5.0}` makes that pairing automatic — the pin
follows the CANN the wheel will actually run against — and the image is already a
complete toolchain for the build (python 3.11 venv with pip/ninja/pybind11,
gcc/make/cmake/binutils, git/curl/tar, torch + torch_npu), so the builder stage
adds no apt step: only the two prebuilt inputs below. Same rule as the Megatron
wheel builder: build env == delivery env.

**Two stages, one file**, the shape the other four have. `--target builder` is
the runtime image plus the two prebuilt inputs staged into FlagTree's offline
caches, and is what `flagtree-builder.yml` publishes; the default target clones
the ref and compiles on top of it. The cold/warm knob is the same `BUILDER_IMAGE`
arg every other backend uses — pointed at the published stage, the staging below
the marker guard is a no-op, which is what spares a warm build the ~2.4 GB of
prebuilt deps (LLVM 2198.6 MiB + triton deps 238.0 MiB on the 9.0.0 line).

Both stages are **published** (2026-10-18, `flagtree-builder.yml` run
39130538293 with `push: true`). Manifest digests, as the registry reported them
on push:

```
flagos-dev/flagtree-builder-ascend-cann9.0.0:2.3.0  sha256:c8ec13f3b309902bbfddcbc02929e93b81d9de863da325af033d8f5cfe7a006c
flagos-dev/flagtree-builder-ascend-cann8.5.0:2.3.0  sha256:26398afb000b13ec24e9418b5722deafcb1ada244dc31d29906be7ac59efe6fa
```

The push step then reads each ref back and compares the served image against the
local one, so what a wheel line pulls is the image this repo built.

| | `ascend-cann9.0.0` | `ascend-cann8.5.0` |
|---|---|---|
| Base image | `flagos-runtime-ascend-cann9.0.0:{version}` | `flagos-runtime-ascend-cann8.5.0:{version}` |
| FlagTree branch (default) | `triton_v3.5.x` (build dir = repo root) | `triton_v3.2.x` (build dir = `python/`) |
| Prebuilt LLVM | `llvm-7d5de303-…-compat_v0.6.0` | `llvm-a66376b0-…-compat_v0.3.0` |
| triton build deps | `build-deps-triton_3.5.x-linux-aarch64` | `build-deps-triton_3.2.x-linux-aarch64` |
| Wheel version | `0.7.0+ascend3.5.<UTC date>` | `0.6.0+ascend3.2.<UTC date>` |

The default ref is a **vendor release branch, not `main`**: the two CANN lines
track their own (3.5 for CANN 9.0.0, 3.2 for CANN 8.5.0) and neither follows
upstream's tip, which is what the layout note in the table reflects — 3.5 keeps
`setup.py` at the repo root, 3.2 keeps it in `python/`. The wheel's version label
keeps the vendor's `+ascend3.5` / `+ascend3.2` spelling — that is what the
`configs.yaml` pins and the backend docs reference — while the file is named
after the backend.

Notes that apply only here:

- **`PYTHONPATH` must be dropped during the build, the gate and the smoke test.**
  The runtime image's `/etc/profile.d/zz-compiler.sh` puts the *vendor* FlagTree
  (`/opt/flagtree`) on `PYTHONPATH` in every bash shell, so a naive
  `import triton` imports the vendor wheel. The source is cloned to
  `/opt/flagtree-src` (never `/opt/flagtree`), and the smoke installs into
  `/opt/wheel-test` and asserts `triton.__file__` plus the distribution version.
  `verify_ascend_wheel.py` is run with `PYTHONPATH=` for the same reason: its
  internals check has to read the pybind11 the build installed, not the vendor
  flagtree's tree.
- **Two build-time pins, two different contracts.** `PYBIND11_VERSION` (default
  `3.0.3`) is an ABI contract with the runtime: an unpinned install pulls 3.1.x,
  which imports fine but breaks at kernel-compile time on hardware.
  `NANOBIND_VERSION` (default `2.4.0`) is a contract with the prebuilt LLVM
  instead — its `MLIRDetectPythonEnv.cmake` asks for 2.4, and nanobind 3.x
  rejects that request, failing the build in cmake. Both are named `_VERSION`,
  not the `_SPEC` of the older builders: ARG splits on the first `=`, so
  `ARG X==3.0.3` would hand pip `pybind11=3.0.3`.
- **The internals gate compares, it does not pin.** A pybind11 internals version
  written as a literal here would be a second place for the pin to live and drift
  from. Instead the gate reads `PYBIND11_INTERNALS_VERSION` out of the
  *installed* pybind11's own `internals.h` — the way FlagTree's own
  `_installed_pybind11_internals()` does — and fails if `libtriton.so` or any
  other shipped `.so` disagrees with it.
- **The CANN version is a gate, not decoration**: `CANN_VERSION` is compared
  against the toolkit found in the image, so a wrong `BUILDER_IMAGE` fails the
  build instead of producing a wheel built against the wrong CANN. The gate reads
  the install-info file the image actually ships — flagtree reads only
  `ascend_toolkit_install.info`, which CANN 9.0.0 does not ship, so the 3.5 build
  logs `CANN version not detected` and takes its default pin (the cann9.0.0 line,
  correct for this image, and the gate is what proves it).
- **The source commit travels in a `setup.cfg` carrier**, like `nvidia-cuda`:
  neither branch ships a `setup.cfg` and neither `pyproject.toml` has a
  `[project]` table, so the file the build writes merges into METADATA on its
  own; `verify_ascend_wheel.py` asserts the resulting `Source-Commit`
  `Project-URL` is there exactly once — the contract the `daily:` row below
  relies on.
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
  what a real build must use. That input reaches the build as
  `--build-arg BUILDER_IMAGE`, the same arg every other backend's cold base uses.
- **The proxy is the runner's, like every other builder.** The targets declare
  `http_proxy` / `https_proxy` / `no_proxy` and `flagtree-wheel.yml` relays all
  three verbatim; git, curl and pip read them on their own, and nothing in the
  build probes reachability or decides for the runner which endpoints are direct.
  A host a build must reach directly is therefore named in the runner's
  `no_proxy`, not in this tree.
- **`$ASCEND_HOME` is a symlink.** It resolves to
  `/usr/local/Ascend/ascend-toolkit/latest -> /usr/local/Ascend/cann`, and the
  install-info files sit two levels below it under `aarch64-linux/`. A `find`
  starting at it needs `-H`: without it `find` reports the link and stops, so a
  probe silently finds nothing (the builder line's `ascend` stage check failed
  this way in 39125616448). `verify_ascend_wheel.py` is unaffected — Python's
  `open` follows symlinks on its own.
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
- **Both rows are on the daily line, each tracking its own branch.** The daily
  does not build upstream's `main` here: ascend has not moved to triton 3.6, so
  the 3.5 and 3.2 lines are where this backend's fixes land, and each `daily:`
  row names its branch as `ref`. That is the same shape as every other backend's
  row — what differs is only that the ref is a vendor line rather than `main`.
  A date-stamped wheel of a branch that did not move is still a wheel of a new
  date, and the commit it was built from travels in its METADATA.
- **Their wheel tags are `cp311`/`aarch64`, not the `cp312`/`x86_64` of the
  `ubuntu:22.04` stages.** The build machine is the CANN runtime image, so the
  interpreter is the one that image ships. The `daily.wheel_tag` a row declares
  is checked against what the build produced, so a wrong one fails the run rather
  than publishing a wheel no CANN node can install.
- **The distribution name is dotted, and that reaches the index.** A daily
  publishes under `flagtree-ascend-cann9.0.0`, whose canonical (PEP 503) form is
  `flagtree-ascend-cann9-0-0` — dots are separators, not part of the name. Nexus
  serves only the canonical spelling, and a wheel's file name is a third string
  again (`flagtree_ascend_cann9_0_0-…`, `bdist_wheel`'s escaping). The plan job
  derives both, which is why the daily's skip probe reads
  `…/simple/flagtree-ascend-cann9-0-0/` and not the name the row declares.
  Consumer-side the declared name is the right one: pip, and
  `importlib.metadata`, normalize it themselves.

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

# ascend pair: aarch64 only, and the builder stage's cold base is the backend's
# runtime image (pulled from the registry if absent). The build clones github.com
# and fetches prebuilt deps, so the same three proxy args apply.
docker build -t flagtree-ascend-cann9.0.0:0.7.0 -f ascend-cann9.0.0 .

# ...and the same split as nvidia-cuda above, on the published stage:
docker build --target builder -t flagtree-builder-ascend-cann9.0.0:ci -f ascend-cann9.0.0 .
docker build --build-arg BUILDER_IMAGE=flagtree-builder-ascend-cann9.0.0:ci \
             -t flagtree-ascend-cann9.0.0:0.7.0 -f ascend-cann9.0.0 .
```

Useful build args (see the Containerfile for the full list):

- `FLAGTREE_VERSION` — FlagTree git branch/tag/sha to build; also the wheel version
  string (default `0.7.0` for `nvidia-cuda`, `0.7.0+metax3.6` for `metax`,
  `0.7.1a1+iluvatar3.6` for `iluvatar`, `0.7.0+sunrise3.6` for `sunrise`). This
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
  under. Default `flagtree`; the daily line sets `flagtree-<backend>` (see below).
- `FLAGTREE_PYPI_KEY` — unlocks the clean version (md5-gated in FlagTree's
  `setup.py`). Set by no caller in this repo.
- `BUILDER_IMAGE` — the staged builders (every Containerfile here has one). The
  image stage 1 builds on; defaults to `ubuntu:22.04` (the cold build) except on
  the ascend pair, whose cold base is the backend's runtime image and is therefore
  a registry ref. Pointing it at the published builder stage makes stage 1 a no-op
  — see the builder sections above. This is also the arg `flagtree-wheel.yml`'s
  `base_image` input reaches the build as.

The build runs in `Release` mode, which strips `libtriton.so` (~840 MB → ~150 MB)
and drops asserts. A smoke test installs the freshly built wheel and imports
`triton`, failing the build if the wheel is broken. `nvidia-cuda` additionally
patches `python/flagtree/__init__.py` after the clone, and it and the ascend pair
record the source commit (see below).

## Daily builds

`.github/workflows/flagtree-wheel-daily.yml` builds one wheel per day and
publishes it to `flagos-pypi-daily`, one distribution per backend that has an
enabled `daily:` row — `flagtree-nvidia`, `flagtree-metax`,
`flagtree-iluvatar`, `flagtree-sunrise`, `flagtree-enflame`, `flagtree-hcu`,
`flagtree-tsingmicro` and the ascend pair today. The release line
(`flagtree-wheel.yml`, manual) is untouched: it keeps publishing plain
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

Three knobs per backend, all in `packaging/flagtree/backends.yaml`'s `daily:`
block: `version_base` (the release this daily leads — move it when `configs.yaml`
moves on), `dist_name` (names the wheel) and `ref` (the FlagTree line that row
tracks — upstream's `main` everywhere but the ascend pair, which tracks its own
`triton_v3.5.x` / `triton_v3.2.x`). `ref` is declared rather than taken from the
Containerfile's own default, which is the vendor release a local build
reproduces. `wheel_tag` is the interpreter and platform the wheel wears: `cp312`
on the deadsnakes stages, `cp310` on sunrise (its 22.04 system python) and
`cp311`/`aarch64` on the ascend pair (its CANN runtime image).

**One distribution, three spellings of its name.** `dist_name` is what
`setup.py` is handed (`flagtree-ascend-cann9.0.0`); the file on the index is
`bdist_wheel`'s escaping (`flagtree_ascend_cann9_0_0-0.7.0.dev<date>-cp311-cp311-linux_aarch64.whl`);
the index path is the PEP 503 canonical form (`flagtree-ascend-cann9-0-0`). The
plan job derives the second and the third from the first, so the skip probe and
the filename gate agree with what lands — for the dashed names the three happen
to coincide, which is why nothing here noticed until a dotted one arrived.

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

**The date is the version, so a missed day does not come back.** The plan
computes `<version_base>.dev<today's UTC date>` and takes no date input; a
dispatch made later publishes the later date. An unpublished day is therefore a
permanent gap in that backend's daily line — 2026-10-18 is one, for every
backend, because the plan's 404-tolerance line was written to stdout and took
`matrix.json` with it, leaving the build matrix empty (#1411).

**A failed plan must not read as a green day.** The plan reaches the build job
through `$GITHUB_OUTPUT`, and an empty matrix *skips* the build job rather than
failing it — so a plan that dies still concludes the run `success`. The matrix is
therefore assigned to a variable before it is written: `matrix="$(jq -c . …)"`
carries jq's exit status into `set -e`, where the one-line
`echo "matrix=$(jq …)"` discards it. Both flagtree lines emit the matrix this way
(#1411's second half).

**And it builds on the published builder stage** (see the NVIDIA builder section
above): the `builder_image` input takes an override, and blank means the ref
derived from `build-config.yml` + `configs.yaml`. `ubuntu:22.04` is the cold path
and the fallback for before the builder has been published.

**Which rows it builds.** The schedule always builds every enabled row. A manual
dispatch may name rows instead, through the `backends` input — which is what
keeps a one-backend check from occupying every other backend's runner, and is
how a row is exercised before `enabled` is flipped (naming a row reaches a
disabled one, since `enabled` says whether the *schedule* builds it). An unknown
name fails the plan rather than dropping the row: an empty matrix skips the
build job and still concludes the run green.

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
