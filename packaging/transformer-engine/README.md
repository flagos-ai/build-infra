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

# TransformerEngine-FL wheel builder

**`DESIGN.md` is the design of record** — why this is a pure-Python
`py3-none-any` wheel, why NVIDIA is excluded, and how the `+fl` version is
formed. This file is only how to run it.

Builds the **pure-Python dispatch-layer `transformer_engine` wheel** from
TransformerEngine-FL (`TE_FL_SKIP_CUDA=1`) and uploads the one wheel to every
**non-NVIDIA** vendor PyPI plus the daily index.

Like `packaging/flaggems/` (and unlike `packaging/flagcx/`, which compiles
native device code in a builder image), this wheel carries no native code, so it
is a plain script plus a workflow — no vendor toolchain, no builder image, no
per-backend matrix.

## Build

`build.sh` only builds (uploading is the workflow's job):

```sh
# from a release tag — the version is the tag minus its leading `v`
TE_FL_REF=v2.17.0+fl.0.3.0 ./build.sh

# or state the version outright (non-tag ref)
TE_FL_VERSION=2.17.0+fl.0.3.0 TE_FL_REF=main ./build.sh

# from a local clone / custom output dir
TE_FL_REPO=/path/to/TransformerEngine-FL ./build.sh
OUTDIR=/tmp/wheels ./build.sh
```

The build fails loudly if the wheel is not `py3-none-any` (TE_FL_SKIP_CUDA did
not take) or if the version carries no `+fl.<flver>` local label.

## Release (build + fan-out to all non-NVIDIA vendor PyPIs)

Driven by `scripts/release_te_fl.py`, run from the workflow
`.github/workflows/te-fl-release.yml`:

```sh
python3 scripts/release_te_fl.py build-python  --ref v2.17.0+fl.0.3.0
python3 scripts/release_te_fl.py upload-python  wheels/transformer_engine-2.17.0+fl.0.3.0-py3-none-any.whl
#   --dry-run lists the lanes without uploading
```

`NEXUS_TOKEN` (`user:token`) is required for upload. NVIDIA is never a lane —
see `NON_TE_FL_VENDORS` in the script and the reason in `DESIGN.md`.

## Installing the wheel

The wheel declares its runtime deps (`torch>=2.1`, `einops`, `onnx`,
`onnxscript`, `nvdlfw-inspect`, `pydantic`, …) — `import
transformer_engine.pytorch` needs them. The vendor index holds none of these,
so an install resolves them elsewhere: pass `--extra-index-url` for a PyPI
mirror, or pre-provide them in the runtime/app image. Installing with
`--index-url <vendor>` alone fails on `pydantic`/`onnxscript` not found.

