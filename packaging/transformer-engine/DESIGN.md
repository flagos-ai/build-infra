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

# TransformerEngine-FL wheel — design of record

`README.md` is how to run it; this file is why it is shaped the way it is.

## What this wheel is

TransformerEngine-FL (TE-FL) is a fork of NVIDIA TransformerEngine that adds a
**plugin dispatch layer** (`transformer_engine.plugin`), so a training stack that
imports `transformer_engine` can route its ops to FlagGems/Triton or to a vendor
backend instead of NVIDIA CUDA kernels. This line ships **only that dispatch
layer**, built with `TE_FL_SKIP_CUDA=1`:

- `setup.py` then emits `ext_modules=[]` — no native code, a `py3-none-any`
  wheel. The native per-SDK pieces are **not** in here: a vendor's own
  `transformer_engine_<vendor>` and FlagGems are discovered at runtime (both are
  optional `try: import`, gated by `_build_config`), not bundled.
- So the wheel is **not a function of the SDK**: one build serves every backend
  of every vendor. That is what lets it be built once and fanned out, like the
  pure-Python `flag_gems` wheel.

## Decisions taken

| Question | Decision |
|---|---|
| Payload | Dispatch layer only (`TE_FL_SKIP_CUDA=1`), `py3-none-any`. No native ext. |
| Build env | Any node — pure Python, no vendor toolchain, **no builder image**. |
| Identity axis | None below the vendor. The wheel bytes are vendor- and SDK-independent, so **no backendlabel** (contrast `packaging/flagcx/`, whose `.so` *is* an SDK function and needs one). |
| Distribution | Build once, upload the same wheel to **every non-NVIDIA vendor index** (`flagos-pypi-<vendor>`) + the daily index. |
| NVIDIA | **Excluded.** On NVIDIA the native path is stock TE and the dispatch layer adds nothing (it even defaults to the slower `flagos` path); NVIDIA uses the official TransformerEngine. |
| Version | `<upstream>+fl.<flver>`, e.g. `2.17.0+fl.0.3.0`. |

## Why NVIDIA is not on this line

TE-FL's native build is NVIDIA-CUDA-specific (nvcc / `CMAKE_CUDA`), so a native
TE-FL build on NVIDIA produces exactly stock TE's kernels — no gain. The only
thing the fork adds there is the dispatch indirection, whose default
(`TE_FL_PREFER=flagos`) would route NVIDIA ops to FlagGems/Triton, slower than
TE's own CUDA. NVIDIA therefore stays on the official TransformerEngine; this
line never uploads to `flagos-pypi-nvidia`. The exclusion lives in
`scripts/release_te_fl.py` (`NON_TE_FL_VENDORS`).

## Version — upstream public, FL version in the local label

The public segment **must** equal the upstream TE version the fork tracks
(`2.17.0`), because Megatron gates features on `transformer_engine.__version__`
via `is_te_min_version(...)`: a public segment of `0.3.0` (the FL version) would
read as "older than 2.3.0" and silently disable every TE feature. So the FL
version goes in the **local label**, where `==`/`>=` comparisons ignore it —
`2.17.0+fl.0.3.0`. This is the `v2.9.0+fl.0.1.0` convention already in TE-FL's
tag history, not a new one.

TE-FL has no setuptools_scm; `te_version.py` reads `build_tools/VERSION.txt`,
which carries only the upstream version on every tag (the FL version is in the
tag *name*). `build.sh` therefore writes the full `<upstream>+fl.<flver>` into
VERSION.txt of its throwaway clone before building — the string is the release
tag minus `v` — and sets `NVTE_RELEASE_BUILD=1` so `te_version.py` does not
append a `+<sha>` and make a second `+`.

## Why the local label is load-bearing, not cosmetic

The goal is that Megatron-LM-FL resolves `transformer-engine` to **our** wheel,
never stock TE from PyPI or a vendor's own fork off an extra index.

- **Primary guard: index isolation.** The vendor image installs from
  `flagos-pypi-<vendor>` only; the public PyPI / an NVIDIA extra index is not on
  the search path.
- **Secondary guard: the `+fl` local label.** PEP 440 makes a version with a
  local label sort **above** the same public version without one, so on a tie
  (`2.17.0` stock vs `2.17.0+fl.0.3.0`) ours wins. It is not a convention
  operators can skip: a bare `2.17.0` on another index would otherwise shadow us
  on a public-version tie.

A plain-`transformer_engine` import in Megatron (`is_te_min_version` etc.) is
satisfied unchanged, since the public `2.17.0` segment is what those checks read.

## What is NOT decided here

- **Wiring the pin into images.** For Megatron to actually install this wheel, a
  non-NVIDIA backend must carry `transformer_engine==<ver>` in `configs.yaml`
  (`deps` / `deps_app`) the way `hygon` carries its vendor TE today. That change
  is per-vendor and gated on FlagGems op coverage for the ops Megatron triggers
  on that chip — tracked with the Megatron-LM-FL integration, not here.
- **Op coverage.** Whether the `flagos` path actually covers a given chip's
  Megatron workload (vs falling back to `reference`) is a correctness question
  for that vendor, independent of packaging.
