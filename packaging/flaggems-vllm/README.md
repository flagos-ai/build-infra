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

# FlagGems-vllm daily wheel builder

Builds the **pure-Python `flaggems_vllm` wheel** from FlagGems-vllm `main` to
`flagos-pypi-daily`. Same shape as `packaging/flaggems/`: `py3-none-any`, so no
vendor toolchain and no container — a plain venv script plus a workflow. The
one thing that differs is where the version comes from, below.

This is the **daily** line only. The **release** line is the `flaggems_vllm`
row of `packaging/flaglibs/`, built from the upstream release tag to
`flagos-pypi-hosted`; the two publish different versions to different indexes
and neither replaces the other — the same relationship `flaggems-wheel.yml` and
`flaggems-release.yml` have.

## Version rule

FlagGems reads its version from git via `setuptools_scm`; FlagGems-vllm has no
scm, so the version is a **static string** in `pyproject.toml` and that string
is what the rule reads. Two cases, the same two `packaging/flaggems/build.sh`
handles:

| ref | version | example |
|---|---|---|
| an upstream release tag | the tag — the tag decides, per `packaging/flaglibs/docs/decisions.md` D4 | `v0.2.0` → `0.2.0` |
| anything else (the daily, off `main`) | the static version's base + the UTC date | `0.3.0-dev1` → `0.3.0.dev20261104` |

The base is upstream's — its development line is spelled `X.Y.0-devN`, so the
rule strips the dev suffix and appends the date, and invents nothing. The dated
form sorts above the declared dev version and below the release it precedes,
which is what a build off the development line should be.

Whichever version comes out is written into the throwaway clone's
`pyproject.toml`, never upstream, and written back to be read: `[tool.*]`
sections carry `version = ` lines too, and a rewrite that landed on one of
those would build the static value silently.

The tag case exists because a manual dispatch can name a tag; the daily always
takes `main`. When a tag and the static string disagree the build prints a
WARNING and ships the tag. Upstream currently has one such tag: the annotated
`v0.2.0` dereferences to commit `b5c2c224`, whose `pyproject.toml` declares
`0.1.0`. The `flaglibs` row builds that same tag and ships the string, so the
two lines name the same ref differently until upstream re-tags — `flaglibs`
does not implement its own D4. Nothing here depends on that being fixed.

## Build

`build.sh` only builds; uploading is the workflow's job.

```sh
FLAGGEMS_VLLM_REF=main ./build.sh                      # default ref
FLAGGEMS_VLLM_REPO=/path/to/FlagGems-vllm ./build.sh   # from a local clone
OUTDIR=/tmp/wheels ./build.sh                          # choose the output dir
```

Two gates, both against a silent publish rather than a compile failure:

- the wheel is `py3-none-any` at exactly the version above — a platform tag
  means the build hit a C++ backend, a different version means the rule missed
  the field the build backend reads;
- every `*.yaml` under `src/` is in the wheel. Those are the per-backend tune
  configs, shipped through `[tool.setuptools.package-data]`; a wheel that loses
  them still imports, and finds no configs on a node. A comparison and not a
  count, because the count is a property of the ref (v0.1.0 carries four).

## Daily workflow

`.github/workflows/flaggems-vllm-wheel.yml`:

- **Schedule** (daily 01:27 UTC) → builds and **uploads** to
  `flagos-pypi-daily`.
- **Manual dispatch** → inputs `flaggems_vllm_ref`, `pypi_repo`, `upload`
  (default `false`, so building from a branch is safe).
- Auth via the org secret `NEXUS_TOKEN`, through the shared uploader image
  (`packaging/upload/upload-wheels.sh`) — never twine on the runner's python.

The wheel carries a date, so a new day is a new version even when the ref has
not moved. Not wired into `record-wheel-info`, for the same reason the FlagGems
and FlagTree dailies are not: the catalog would gain a row per day. See
`docs/wheel-info.md`.
