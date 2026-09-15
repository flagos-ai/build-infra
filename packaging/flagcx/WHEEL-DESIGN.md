# FlagCX wheels — build-infra side

Status: **conclusions only, nothing built.** No wheel exists in this tree. `DESIGN.md` is the deb
line's design of record; this file is the wheel line's, and it covers only what build-infra decides.
The FlagCX-side questions — what goes inside the wheel, what the public API is — live in
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
