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

# flaggems-builder

Builds the **pure-Python `flag_gems` wheel** from FlagGems source and uploads it
to the internal PyPI, daily.

Unlike `flagtree-builder/` (which needs an old-glibc container to compile
native code), the pure-Python wheel is platform-independent (`py3-none-any`) and
needs **no vendor toolchain** — so this is a plain script plus a workflow.

The wheel version comes from **FlagGems' own `setuptools_scm`** (its git tags),
e.g. `flag_gems-5.4.0.dev580+gb89e0aeb8-py3-none-any.whl`. We do not inject a
version; the checkout just has to include tags.

> The per-vendor **C++ operator** wheels (`flag-gems-cpp-<vendor>`) are a
> separate, rarely-rebuilt artifact that *does* need a base image to compile —
> not built here. See the design doc (§3).

## Build

`build.sh` only builds (uploading is the workflow's job):

```sh
# from a ref (default: master)
FLAGGEMS_REF=master ./build.sh

# from a local clone, offline
FLAGGEMS_REPO=/path/to/FlagGems ./build.sh

OUTDIR=/tmp/wheels ./build.sh        # choose the output dir (default ./wheels)
```

It clones FlagGems (with tags), runs `pip wheel . --no-deps`, and fails loudly
if the result isn't a `py3-none-any` wheel (a platform tag would mean the build
hit the C++ backend — wrong ref or packaging).

## Daily workflow

`.github/workflows/flaggems-wheel.yml`:

- **Schedule** (daily) → builds and **uploads** to the internal PyPI.
- **Manual dispatch** → inputs `flaggems_ref`, `pypi_repo`, and `upload`
  (default `false`, so building from a branch is safe). Always uploads the wheel
  as a GitHub Actions artifact for inspection.
- Upload target: **`flagos-pypi-daily`** (the daily/dev repo; releases go to
  `flagos-pypi-hosted`). Auth via the org secret `NEXUS_TOKEN` (`user:token`).
