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

## Two-layer build

The expensive apt/pip setup is baked into a **toolchain image** once per Python
version and pushed to Harbor, then every wheel build starts from it — no
re-installing everything from scratch on each run (the flagtree-builder pain
point).

```
packaging/megatron/builder/Containerfile
 ├─ stage "toolchain"  →  FROM ubuntu:22.04 + deadsnakes Python + build deps  ← built ONCE, pushed
 └─ stage "wheel"      →  FROM ${BASE_IMAGE=toolchain image}                  ← every wheel build
```

### 1. Toolchain image (rarely rebuilt)

```sh
# once per Python version; run from inside packaging/megatron/builder/
VERSION=$(python3 -c "import yaml;print(yaml.safe_load(open('configs.yaml'))['version'])")
docker build --target toolchain --build-arg PYTHON_VERSION=3.12 \
    -t harbor.baai.ac.cn/flagos-dev/megatron-builder-py312:${VERSION} .
docker push harbor.baai.ac.cn/flagos-dev/megatron-builder-py312:${VERSION}
```

Only rebuilt when the pins change. It contains, on **ubuntu:22.04** (glibc 2.35,
so the `.so` loads on older-glibc nodes):

- `python3.{10,11,12}` via deadsnakes, `build-essential`, `git`, `unzip`
- `setuptools<80.0.0 wheel pybind11==3.0.3 numpy==1.26.4 packaging>=24.2`

**pybind11 and numpy are ABI contracts, not just versions:**

- **pybind11==3.0.3** matches the runtime images' pin (`runtime_prereqs` /
  `flaggems_cpp_build_deps` in configs.yaml). `helpers_cpp` and the runtime's
  own pybind11 share type registries, and a mismatch (3.1.0 bumped internals to
  v12) breaks the extension at call time — the flagtree-builder lesson.
- **numpy==1.26.4** (1.x headers): the `.so` then runs on both numpy 1.x and 2.x
  runtimes, while a 2.x-built `.so` requires numpy≥2. hygon pins numpy==1.26.4,
  so this is the lowest common denominator.

### 2. Wheel stage (every build)

```sh
VERSION=$(python3 -c "import yaml;print(yaml.safe_load(open('configs.yaml'))['version'])")
docker build \
    --build-arg BASE_IMAGE=harbor.baai.ac.cn/flagos-dev/megatron-builder-py312:${VERSION} \
    --build-arg MLF_REF=main \
    -t megatron-wheel:py312 .
cid=$(docker create megatron-wheel:py312)
docker cp $cid:/wheels/. ./wheels
docker rm $cid
ls wheels/*.whl   # megatron_core-0.17.1-cp312-cp312-linux_x86_64.whl
```

Useful build args:

| ARG            | Default                              | Meaning                                        |
|----------------|--------------------------------------|------------------------------------------------|
| `BASE_IMAGE`   | *(required)*                         | The pushed toolchain image for this Python    |
| `PYTHON_VERSION`| `3.12`                              | Must match the toolchain image's Python       |
| `MLF_REPO`     | `https://github.com/flagos-ai/Megatron-LM-FL.git` | Source repo                  |
| `MLF_REF`      | `main`                               | Branch or tag to build                        |
| `MLF_VERSION`  | *(blank)*                            | Optional wheel-version override (e.g. `0.17.1.post20260812`); blank = the repo's own version (`0.17.1`) |

The wheel stage: clones the fork, **patches `requires-python` on the fly**
(`>=3.12` → `>=3.10`, see below), optionally stamps `MLF_VERSION` into
`megatron/core/package_info.py` (`stamp_version.py`), builds with
`pip wheel . --no-deps --no-build-isolation` (no uv, no lock file), then runs two
gates:

1. **`.so`-in-wheel gate** — `unzip -l /wheels/*.whl` must contain
   `helpers_cpp*.so`; catches the silent `optional=True` skip.
2. **Smoke test** — installs the wheel and loads `helpers_cpp` directly via
   `importlib` (importing `megatron.core` would pull in torch, which the build
   env intentionally lacks), asserting `build_sample_idx_*` are bound.

## requires-python on the fly

The fork's `pyproject.toml` declares `requires-python = ">=3.12"` (tightened from
upstream's `>=3.10` in the 0.17.0 sync). pip enforces Requires-Python at install
time, so the cp310/cp311 wheels would be refused on those runtimes. The wheel
stage patches the source **after clone, before build**:

```dockerfile
RUN cd /opt/megatron-lm-fl \
    && sed -i 's/^requires-python = ">=3\.12"$/requires-python = ">=3.10"/' pyproject.toml \
    && grep -q 'requires-python = ">=3.10"' pyproject.toml
```

The fork repo is **not modified** by this. Relaxing it there is a proposed
follow-up, once this end-to-end path is verified.

## Install into a runtime image

The megatron app image (`app/megatron/Containerfile`) installs the wheel with a
**single-step `pip install` — no `--no-deps`**. The wheel is first **repacked**
by `packaging/megatron/repack/` (reusing `packaging/vllm/repack.py`) to strip
`Requires-Dist: torch` from its METADATA and bump the version to a `+flagos`
suffix; the repacked wheel is uploaded to the per-vendor PyPI index. Then:

```dockerfile
RUN pip install \
  --index-url "${FLAGOS_PYPI}" \
  --extra-index-url "${EXTRA_PYPI}" \
  "megatron-core==${MEGATRON_VERSION}"
```

- The vendor index is searched first — the `+flagos` repacked wheel is found
  and used.
- Torch is already in the runtime venv and satisfies any transitive
  constraints, so pip skips it. `numpy`/`packaging` are pinned per-backend in
  the image and resolved from `EXTRA_PYPI` if missing.
- pip auto-selects the `cp310` / `cp311` / `cp312` wheel matching the image's
  Python.

Why not `--no-deps`: a bare `--no-deps` would refuse to install the repacked
wheel (its version resolution needs the normal resolver), and more importantly
a plain install with deps intact could pull public-PyPI torch over the vendor
build. Stripping torch from METADATA gives the same safety without bypassing
dependency resolution. See `packaging/megatron/repack/report-megatron-0.17.1.md` for the
risk analysis.

- Verify (after `source /opt/dtk-26.04/env.sh` on hygon):

  ```bash
  python -c "import megatron.core; print(megatron.core.__version__)"   # 0.17.1
  ```
