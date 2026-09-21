# FlagCX wheels — build-infra side

Status: **the builder images are built; no wheel exists in this tree yet**, so every decision below
that is about the wheel itself is still a conclusion rather than a shipped thing. `DESIGN.md` is the
deb line's design of record; this file is the wheel line's, and it covers only what build-infra
decides. The FlagCX-side questions — what goes inside the wheel, what the public API is — live in
[flagos-ai/FlagCX#593](https://github.com/flagos-ai/FlagCX/issues/593), not here.

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
tarball — 468 MB extracted, and clang-22 links no `libLLVM`. The one package that is not the
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
build, which is where a stale builder would be consumed.

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
