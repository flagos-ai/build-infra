# FlagCX wheels — build-infra side

Status: **both nvidia rows build a wheel that carries their device bitcode, and it has been
verified end to end on h20** — built in the row's builder image, installed into the row's runtime
image, imported, with the bitcode and its header present. Not yet published to an index.
`DESIGN.md` is the deb line's design of record; this file is the wheel line's, and it covers only
what build-infra decides. The FlagCX-side questions — what goes inside the wheel, what the public
API is — live in [flagos-ai/FlagCX#593](https://github.com/flagos-ai/FlagCX/issues/593), not here.

## Context

The deb line ships one package per backend. A wheel line ships the same library as Python
artifacts, so what differs is not the build but the **identity, pinning and install contract** —
deb has per-package names, `Provides:`, and apt's repo/suite; pip has none of the three.

## Decisions taken

| Question | Decision |
|---|---|
| Identity axis | `(vendor, backend, python, torch backend)`. One wheel per **backend**, not per vendor |
| Chip variants | No wheel variant per chip (910B/910C) — the chip is not a build input |
| Version label | PEP 440 local version label, derived from the backend key minus its `{vendor}-` prefix |
| Install contract | Exact pin only (`==`). A `>=` range is satisfied by every variant |
| Upload target | `flagos-pypi-{vendor}` (`configs.yaml:124`) — index per vendor, artifacts per backend |

## Why one wheel per backend

- **The build cannot tell same-vendor backends apart, and that is not evidence that they agree.**
  Every build-side field is identical across a vendor's backends: ascend's four rows differ in
  nothing at all (`make_flag`, `make_env`, `vendor_libs`, `assert`, `arch`, `glibc_floor`), and the
  other multi-backend vendors differ only in `deb`/`apt`/`glibc_floor`, which no build reads.
  Identical fields mean FlagCX has no knob for the difference — "cannot see it", not "the same".
- **The deb line declines the same gamble.** Every multi-backend vendor except ascend has exactly
  one `default_for_vendor: true` variant; ascend has none. That flag is what makes a variant answer
  to the unqualified `Provides: libflagcx-<vendor>` (`deb-config.py:195`), so no ascend package
  claims to stand in for another.
- What deb can do and a wheel cannot: deb ships four ascend packages because each installs into a
  per-SDK image, which resolves the SDK axis at install time. A wheel has no equivalent exit — see
  Install contract below.

## What does not vary, and why

- **The chip is not a build input.** `grep 910` is empty across `makefiles/`, `flagcx/adaptor/` and
  `flagcx/include/`; `makefiles/ascend.mk` is flat with no conditional, and only
  kunlunxin/nvidia/nvidia_gencode branch at all. The chip is selected by the driver at run time.
- **The SDK version is not a build input either — it is a link-time presence.** `ascend.mk` pins
  `DEVICE_HOME`/`CCL_HOME` to `.../ascend-toolkit/latest` and links `-lascendcl` / `-lhccl` with no
  version in the path or the soname. A wheel therefore records *that* a vendor CCL was present, not
  which one, and any version of that library can satisfy the loader.
- **What does vary** is `FLAGCX_TORCH_BACKEND` ∈ {`vendor`, `flagos`}: different torch package
  (`torch_npu` vs `torch_fl`), a `-DFLAGCX_TORCH_BACKEND_FLAGOS` compile flag, and a `libflagos.so`
  link. The Python version varies with the torch extension, since `flagcx._C` is compiled.

## The build-toolchain image (the `builder` channel)

A wheel is built *inside* the backend's runtime image, and on the nvidia rows that image carries no
device toolchain at all — measured on `flagos-runtime-nvidia-cuda13.3:2.2.0`: no nvcc, no
`cuda_runtime.h`, no `include/cccl`, no `nccl.h`, no clang. Those rows therefore publish one more
artifact beside the wheel: an image that can be the wheel build's environment, under the prefix
`build-config.yml` already reserved for builder images (`registry.prefixes.builder` = `flagos-dev`,
unconsumed until now).

| Question | Decision |
|---|---|
| Base | The row's own **runtime** image — never a vendor `-devel` tag |
| Contents | The row's `apt:` list + `builder.apt` + clang/llvm 22 + the wheel's build-only headers |
| Which rows | Only those declaring `builder.enabled`; a runtime image that already carries the toolchain needs none |
| Acceptance | Compiling that row's device bitcode inside the built image, in CI, before the push |

This is not the pre-built builder the megatron line declined. That decision's reason was that its
runtime image was already sufficient; here it is not, and the invariant that keeps the shape honest
is the same one the wheel line already runs on — **build env == delivery env**, so the builder is a
superset of the row's runtime image and nothing else.

**Why the runtime image and not `nvcr.io/nvidia/cuda:*-devel`.** Measured on h20:

| Image | Size | nvcc | clang/llvm | NCCL | curand header |
|---|---|---|---|---|---|
| `cuda:13.3.0-runtime-ubuntu24.04` | 3.87 GB | ✗ | ✗ | ✗ | ✗ |
| `cuda:13.3.0-devel-ubuntu24.04` | 10.8 GB | ✓ | **✗** | ✗ | ✓ |
| `cuda:12.8.0-runtime-ubuntu24.04` | 5.61 GB | ✗ | ✗ | ✓ (held) | ✗ |
| `cuda:12.8.0-devel-ubuntu24.04` | 14.6 GB | ✓ | **✗** | ✓ (held) | ✓ |

Neither `-devel` tag ships any clang/llvm, so the LLVM pin below is unavoidable on any base, and
13.3's `-devel` carries no NCCL either — that apt step would not go away. A `-devel` base also has
no `/flagos`, so on its own it could not be the wheel's `BASE_IMAGE` at all. The alternative — moving
the flagos base itself onto `-devel` — costs +6.9 GB (13.3) / +9.0 GB (12.8) on every layer above
it, which is how a compiler ends up shipped in delivery images with no consumer.

**LLVM 22 is a floor, not a preference.** CUDA 13 removed `texture_fetch_functions.h`, which clang's
CUDA wrapper included unconditionally through 21, and CUDA 13.2's `crt/math_functions.h` expects the
compiler to define `_NV_RSQRT_SPECIFIER`; both fixes land in 22. Measured against CUDA 13.3: clang-20
(Ubuntu 24.04) and clang-21 (apt.llvm.org) each fail to compile the device bitcode, clang-22
succeeds. Only five binaries and clang's resource directory are taken from the 1.94 GB release
tarball — 468 MB extracted, and clang-22 links no `libLLVM`. The tarball is fetched from the
flagos filestore first and GitHub second, and **every build takes the second route today**: the
filestore copy has not been uploaded (that needs the Nexus token, which is not this line's). Both
routes are sha256-checked against the pin in `build-flagcx-builder.sh`, so the route taken does not
change the artifact. The one package that is not the
compiler's own: clang's `__clang_cuda_runtime_wrapper.h` force-includes `curand_mtgp32_kernel.h`,
which no `cuda-nvcc` package ships, though FlagCX never calls cuRAND.

**Two fields state the row's device bitcode** (`bitcode_arch` → `BITCODE_LIB_ARCH`,
`bitcode_adaptor_flag` → `ADAPTOR_FLAG`), stated rather than derived because the only derivation
available is `makefiles/nvidia_gencode.mk`'s table, and a second copy of it here would drift.
`bindings/ir/nvidia/Makefile` never includes `makefiles/nvidia.mk`, so the comm-traits branch that
file picks for the `.so` by reading `nccl.h` can reach the `.bc` only as a value passed in — without
it the two artifacts disagree about `DeviceAPI::Window`/`Multimem`.

**Staleness is real.** The runtime image is a mutable flat tag, so rebuilding a runtime makes every
builder built on the previous one stale; the order is runtime first, builder second. The image
records `flagos.base_digest` so the comparison can be mechanical — that check belongs in the wheel
build, which is where a stale builder would be consumed, and it compares **index** digests: the
label is written from the runtime image's `RepoDigests` and the registry is asked through
`imagetools`, while the platform manifest digest is a different value (measured on h20 for
`nvidia-cuda13.3`: index `8094e543…`, amd64 manifest `4581c63e…`), so pairing the two would report
every builder as stale.

Pointing the wheel build at one of these images also makes part of `Containerfile.wheel` redundant:
its build-only apt list (`libgflags-dev`, `libgoogle-glog-dev`) is what the builder now carries, and
that step is paid on every `FLAGCX_REF` change today. It stays because the rows without a builder
still need it — the vendor SDK rows build their wheel in the runtime image, which carries neither
header — so removing it would trade one build's copy for another's.

The builder also carries the CUDA math libraries' headers (`libcublas-dev-*`, `libcusparse-dev-*`,
`libcusolver-dev-*`, `libcufft-dev-*`), which the wheel build needs for a reason unrelated to
FlagCX: torch's own headers include them (`ATen/cuda/CUDAContextLight.h` reaches `<cusparse.h>`),
and a CUDA *runtime* image ships the libraries without the headers. They are installed at the
version of the library already in the image, read rather than written down, because apt's candidate
belongs to the newest CUDA release in the repo (13.6 while this row's toolkit is 13.3) and
satisfying it would upgrade `libcublas-13-3` out from under the environment the wheel is delivered
to.

## What the wheel carries, and where

| Path in the wheel | On which rows | What reads it |
|---|---|---|
| `flagcx/lib/libflagcx.so` | all | `flagcx._C`'s `$ORIGIN/lib` rpath, and the device API's net-construction kernels live here |
| `flagcx/_C*.so`, `flagcx/api.py` | all | `import flagcx` |
| `flagcx/lib/libflagcx_device.bc` | rows stating `bitcode_arch` | the consumer links it into its kernels (`extern_libs={...}`) |
| `flagcx/include/flagcx_device_wrapper.h` | rows stating `bitcode_arch` | the same consumer's source includes it |

Both bitcode paths are **inside the package** for the same reason the `.so` is: nothing else a
consumer can see is guaranteed to exist. A consumer locates them from `flagcx.__file__` rather than
from an install prefix, which is also what the deb line's consumers are being moved to — see the
path-resolution half of #570.

**The bitcode switch is `bitcode_arch`.** Where a row states it, the wheel build also compiles the
`.so` with `COMPILE_KERNEL=1`, because the two are one decision: the device net-construction kernels
live in the `.so`, and a `.bc` from an `.so` without them describes a backend whose
`flagcxDevNetSizeOf()` is 0 and whose `_netContexts` stay empty. Stating one without the other is
unrepresentable rather than refused, which is why there is no separate `compile_kernel` field.

**nvcc needs `-std=c++20` for the device translation units** (measured on h20, CUDA 13.3): they
include the vendored `third-party/json`, whose `decltype`-dependent templates need C++20, and
nvcc's own default is below that. The Makefile's `-std=` is a host flag and never reaches nvcc's
front end — `-Xcompiler -std=gnu++17` fails the same way — so the standard is set through
`NVCC_PREPEND_FLAGS`, which leaves the host objects on the standard the Makefile chose. Only
`-std=c++20` was measured to work: nvcc's default, `-std=c++17` and `-Xcompiler -std=gnu++17` each
failed on `json.hpp`.

**The bitcode's `BITCODE_CXX_STD` is `gnu++17` and not the same value**, because there are two
compilers here: the `.bc` is clang's output, and NCCL 2.31's device headers use `typeof`, which
clang drops under `-std=c++17`.

**The bitcode and the headers are packaged by FlagCX's own `setup.py`**, which builds the bitcode
inside `build_extensions` (gated on `FLAGCX_BITCODE_ARCH`) and copies it, with the exported
headers, into the package before the archive is written
([FlagCX #614](https://github.com/flagos-ai/FlagCX/pull/614), first tag `v0.14.0-rc2.post2`). The
line therefore hands `setup.py` the same two facts the registry row states and adds nothing to the
wheel afterwards: the archive and its `RECORD` are written once, by the one process that knows
everything that went into them, and the name a wheel is published under is the name it was built
with.

This replaced a post-build injection step (`inject-bitcode.py`, removed here), which rewrote the
archive under the name it already had and recomputed `RECORD` in PEP 376's spelling. That step was
correct but it was a second author of an artifact: what shipped was not what the build produced,
and every row that wanted a `.bc` depended on the build system carrying a copy of FlagCX's
packaging knowledge.

**Which image the wheel is built in is derived** (`deb-config.py`'s `wheel_base_image`): the
runtime image, or the builder image on a row that publishes one. The builder is the runtime image
plus a toolchain, so the environment the extension is compiled in stays a superset of the one that
installs it, and `--check --channel wheel` refuses a row that states `bitcode_arch` without a
builder — the build would otherwise run where there is no clang and fail one stage later, at the
make.

## Mechanics

- **Version label** `0.13.0+cann9.0.0`, derived from the backend key the way `_build_config.py`
  derives its adaptor flag from `ADAPTOR_MAP` — never hand-written. Dropping the `{vendor}-` prefix
  was checked against all 20 backends: no two vendors collide on the remainder, so the label stays
  unambiguous even if wheels are gathered into one wheelhouse or handed to a customer.
- **The pin belongs in per-backend config, not in operator memory** — the shape `configs.yaml`
  already uses for `flaggems:` (read at `scripts/build_runtime.py:302`, recorded as the OCI label
  `flagos.flaggems` at `:333`). Recording it as a label is what makes "which backend is installed
  here" queryable after the fact.
- **A `--check` gate** in the style of `deb-config.py --check`: a version label without its backend
  suffix fails the build, rather than producing a wheel that silently overwrites its predecessor.
- **pip has no `Provides:`.** The deb line's "the default variant answers to the unqualified name"
  cannot be reproduced. With two variants in one index, `pip install flagcx` does not fail — it
  resolves to the higher local version. The exact pin is therefore load-bearing machinery, not a
  convention that can be left to operators.

## To verify before this is relied on

- **PEP 440 normalization, per backend key** — whether `iluvatar-corex4.4.0` has to be pinned as
  `+iluvatar.corex4.4.0`. The normalized string *is* the pin's value, so it has to be measured
  rather than assumed. `iluvatar_corex`'s underscore already broke the deb name path once;
  `deb-config.py` carries that note.
- **Whether Nexus, or whatever fronts it, decodes a literal `+` in a filename to a space.** Private
  registry, so the public PyPI rule does not bind it — but it has to be observed.
- **The runtime layer, if a wheel's `.so` is ever asked to cross a vendor's SDKs.** Whether one
  SDK's `.so` loads against another's vendor library (e.g. CANN 8.5.0 vs 9.0.0's `libhccl.so`) is a
  per-vendor ABI claim that field inspection cannot answer, and it is not assumed safe. Establishing
  it for a vendor is what would let that vendor's wheel count drop; nothing here depends on it,
  because one wheel per backend routes around the question entirely.

## Depends on FlagCX — tracked in #593, not decided here

- **Whether the wheel is self-contained** (ships the native `libflagcx.so`) or the runtime/.deb
  provides the library and the wheel carries only the Python layer — #593 Q1. Either way the
  `(vendor, python, torch backend)` axes remain, because `flagcx._C` is a compiled torch extension
  with or without the library beside it.
- **The version is hardcoded** (`setup.py:210`, `pyproject.toml:7`, both `0.13.0`), so one version
  can only ever exist as one artifact — a second build from a different commit is a duplicate
  upload that the index rejects or overwrites, and there is no way to pin to a commit at all. See
  Version below; the public part of the version is FlagCX's to declare.
- Not a gap, and checked: `setup.py`'s make invocation forwards a fixed env list (`setup.py:119`)
  that omits `PLATFORM_EXTRA_SRCS` — but no platform depends on it being forwarded. cambricon and
  iluvatar_corex now set it in their own `.mk` ([FlagCX #582](https://github.com/flagos-ai/FlagCX/pull/582)),
  where the comment carries the same reasoning: `device_api/` is not globbed by the Makefile, and
  `-shared` without `--no-undefined` tolerates the unresolved `devApiBackend` until `dlopen`.

## Version — open, because the two lines disagree today

The deb line pins to a **tag**: `debian/changelog.sh` derives the version from the clone's own tags
and exits non-zero on anything it cannot map, so an unreproducible `.deb` is refused rather than
shipped. A wheel line built the same way would inherit that stance: tags only, no arbitrary commit.

The megatron wheel line takes the other stance — `stamp_version.py` writes
`<public>+fl.<commit-date>.g<sha>` into the checkout before building, exactly so a wheel answers
"which code is this?" without a tag existing.

Not decided. Whichever way it goes, the local label composes with the backend label from Mechanics,
backend first (`0.13.0+cann9.0.0.20260814.g<sha>`): PEP 440 compares local segments left to
right, so leading with the backend is what stops a range from crossing into another backend's
variants. And note `stamp_version.py`'s recorded trap — `==` matching **ignores** the local label
entirely, so `==0.13.0` resolves against every variant. The exact pin is load-bearing either way.

## Not started

- The wheel's source: which FlagCX ref or release line it builds from, and whether the line lives
  here (`packaging/flagcx/`) or in a directory of its own.
- flagcx appears in neither `configs.yaml` `deps:` nor `runtime/Containerfile`, so installing it
  into the runtime image is a new install line rather than an edit to an existing one.
