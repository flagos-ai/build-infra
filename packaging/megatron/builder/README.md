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

# Megatron wheel builder

Builds **megatron-core** wheels from the [Megatron-LM-FL](https://github.com/flagos-ai/Megatron-LM-FL)
fork, for single-command install into the pre-built `flagos-runtime-{vendor}-{backend}`
images.

## Why per-Python wheels

`megatron-core` ships a compiled extension, `megatron.core.datasets.helpers_cpp`.
Every wheel is therefore CPython-ABI-specific — **cp310 / cp311 / cp312**, never
`py3-none-any` — and all three must be built and uploaded, because the runtime
matrix uses all three Pythons:

| Python | Vendors                                                        |
|--------|----------------------------------------------------------------|
| 3.10   | kunlunxin, hygon, mthreads, iluvatar, tsingmicro               |
| 3.11   | ascend                                                         |
| 3.12   | nvidia, metax, enflame                                         |

`helpers_cpp` is **mandatory, not optional**: `megatron/core/datasets/helpers.py`
imports it unconditionally, yet `setup.py` declares the extension
`optional=True`. A failed compile is silently skipped, producing a broken wheel.
The Containerfile gates on the `.so` being inside the wheel to catch this.

## Build environment = the backend's runtime image

The wheel is built **inside the backend's own runtime image**
(`flagos-runtime-{vendor}-{backend}:{version}`) — there is no separate
toolchain/builder image. The runtime image provides the exact Python version
and runtime packages the wheel will run on (torch, numpy, pybind11==3.0.3 …),
so:

- **ABI contracts match by construction** — the pybind11 and numpy the `.so`
  compiles against are the runtime's own.
- **Build env == delivery env** — after the wheel builds, it is installed back
  into the same image with a full `pip install` (deps resolved, no `--no-deps`).
  pip checks the wheel's `Requires-Dist` (torch>=2.6.0 …) against the venv: the
  vendor torch satisfies the constraint, pip downloads and overwrites nothing,
  and the dependency matrix is proven intact *in the very image the wheel will
  ship in*.
- No image to pre-build and push. `megatron-builder-*` was a concept image that
  was never built — the megatron-wheel workflow builds directly from the runtime
  matrix (`scripts/generate_matrix.py --runtime`).

One wheel is built per backend in the matrix (e.g. `hygon-dtk26.04`). Whether a
wheel built on one backend is shareable across the other backends running the
same Python version is **decision 6, not yet validated**: a wheel built on the
oldest-glibc runtime (hygon, ubuntu 22.04, glibc 2.35) should load on every
newer-glibc backend, but the reverse is NOT true. Final call pending
per-backend verification — see `packaging/megatron/docs/`.

### Local build (mirrors the workflow)

```sh
# run from inside packaging/megatron/builder/
VERSION=$(python3 -c "import yaml;print(yaml.safe_load(open('configs.yaml'))['version'])")
docker build \
    --build-arg BASE_IMAGE=harbor.baai.ac.cn/flagos-runtime/flagos-runtime-hygon-dtk26.04:${VERSION} \
    --build-arg MLF_REF=main \
    -t megatron-wheel:hygon-dtk26.04 .
cid=$(docker create megatron-wheel:hygon-dtk26.04)
docker cp $cid:/wheels/. ./wheels
docker rm $cid
ls wheels/*.whl   # megatron_core-0.17.1+fl.20260814.gba22f6b673f3-cp310-cp310-linux_x86_64.whl (date+sha = cloned commit)
```

Useful build args:

| ARG            | Default                              | Meaning                                        |
|----------------|--------------------------------------|------------------------------------------------|
| `BASE_IMAGE`   | *(required)*                         | The runtime image for this backend            |
| `EXTRA_PYPI`   | `https://mirrors.aliyun.com/pypi/simple` | CN mirror for build deps                 |
| `MLF_REPO`     | `https://github.com/flagos-ai/Megatron-LM-FL.git` | Source repo                  |
| `MLF_REF`      | `main`                               | Branch or tag to build                        |
| `MLF_VERSION`  | *(blank)*                            | Wheel-version override (e.g. `0.17.1+fl.0.2.0` for a release build); blank = auto-derived commit provenance `0.17.1+fl.<date>.g<sha>` |

The Containerfile: clones the fork, **patches `requires-python` on the fly**
(`>=3.12` → `>=3.10`, see below), stamps the wheel version into
`megatron/core/package_info.py` (`stamp_version.py`) — by default the
**commit-level provenance label** `0.17.1+fl.<date>.g<sha>` (public part =
upstream megatron-core version, `fl.<date>.g<sha>` = the fork commit's date and
the exact commit cloned; PEP 440 ignores local labels in `==0.17.1` matching,
so existing pins keep resolving) — installs the missing build
deps into the runtime venv, builds with `pip wheel . --no-deps
--no-build-isolation` (no uv, no lock file; `--no-deps` here means "don't build
torch from PyPI", it is not an install), then runs two gates:

1. **`.so`-in-wheel gate** — a `python -c` zipfile scan (runtime images don't
   ship `unzip`) must find `helpers_cpp*.so`; catches the silent
   `optional=True` skip.
2. **Smoke test** — installs the wheel with a full `pip install` (deps
   resolved) and loads `helpers_cpp` directly via `importlib` (importing
   `megatron.core` would need the vendor SDK env sourced, which `docker build`
   RUN can't do — that check belongs to
   `packaging/megatron/verify/verify-megatron-backend.sh`), asserting
   `build_sample_idx_*` are bound.

## requires-python on the fly

The fork's `pyproject.toml` declares `requires-python = ">=3.12"` (tightened from
upstream's `>=3.10` in the 0.17.0 sync). pip enforces Requires-Python at install
time, so the cp310/cp311 wheels would be refused on those runtimes. The wheel
build patches the source **after clone, before build**:

```dockerfile
RUN cd /opt/megatron-lm-fl \
    && sed -i 's/^requires-python = ">=3\.12"$/requires-python = ">=3.10"/' pyproject.toml \
    && grep -q 'requires-python = ">=3.10"' pyproject.toml
```

The fork repo is **not modified** by this. Relaxing it there is a proposed
follow-up, once this end-to-end path is verified.

## Install into a runtime image

The megatron app image (`app/megatron/Containerfile`) installs the wheel with a
**single-step `pip install` — no `--no-deps`**:

```dockerfile
RUN pip install \
  --index-url "${FLAGOS_PYPI}" \
  --extra-index-url "${EXTRA_PYPI}" \
  "megatron-core==${MEGATRON_VERSION}"
```

- The wheel keeps its `torch>=2.6.0` Requires-Dist — no repack, no METADATA
  surgery (the repack facility was removed; that was the vllm sdist path, where
  torch must be stripped because the sdist's deps would pull public-PyPI
  torch over the vendor build. megatron is a fork-source path: the runtime's
  vendor torch satisfies the constraint, so pip resolves nothing).
- Torch is already in the runtime venv and satisfies any transitive
  constraints, so pip skips it. `numpy`/`packaging` are pinned per-backend in
  the image and resolved from `EXTRA_PYPI` if missing.
- pip auto-selects the `cp310` / `cp311` / `cp312` wheel matching the image's
  Python.

The build-time smoke test above is the same single-step install, run in the
build image — proof that the install is inert before the wheel is published.

- Verify (after `source /opt/dtk-26.04/env.sh` on hygon):

  ```bash
  python -c "import megatron.core; print(megatron.core.__version__)"   # 0.17.1+fl.20260814.gba22f6b673f3
  ```
