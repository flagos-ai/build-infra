# FlagGems packaging — design

Status: **implemented.** `README.md` is the operator-facing companion (how to run the
build, what the workflow inputs mean); this file is the design of record — why, not what.
The live answers to "which backends build a cpp wheel" are `scripts/cpp_matrix.py` (filters
`generate_matrix.py` to rows with a `cmake_backend`) and `scripts/release_flaggems.py`
(the release path: build/upload/update-config).

Goal: ship FlagGems two ways — a pure-Python `flag_gems` wheel and per-cmake-backend
`flag_gems_cpp_*` operator wheels — plus the `python3-flag-gems` `.deb`, each on the right
index with a version that is FlagGems' own.

## Context

FlagGems is **pure Python** at the `flag_gems` level, with an optional C++ operator
library per backend family. That single fact splits the packaging three ways:

| Channel | Product | Built how |
|---|---|---|
| python wheel | `flag_gems-<ver>-py3-none-any.whl` | plain script (`build.sh`), **no container** |
| cpp wheel | `flag_gems_cpp_<backend>-<ver>.whl` | inside `runtime:v1` (`{version}-build`), `docker run` |
| deb | `python3-flag-gems` | upstream `packaging/debian/`, release path here only |

`py3-none-any` needs no vendor toolchain and carries no glibc floor, so the python wheel
is the one line here that is a script plus a workflow — unlike flagtree and flagcx, which
compile native code and therefore need a container and a floor.

### Decisions taken

| Question | Decision |
|---|---|
| Python wheel build | No Containerfile: `py3-none-any` is platform-independent, so `build.sh` clones FlagGems (with tags), runs `pip wheel . --no-deps` in a throwaway venv, and uploads nothing — uploading is the workflow's job |
| Version, python wheel | **FlagGems' own setuptools_scm** (its git tags), never injected. `SETUPTOOLS_SCM_PRETEND_VERSION` is deliberately not used, because it makes scm skip git and drop `__commit_id__`. For a non-tag HEAD the daily stamps a throwaway **local** tag `<base>.dev<UTC date>` on HEAD (never pushed, dies with the clone), so scm keeps reading git and `_version.py` carries both the date version and the real commit |
| Platform gate | The build fails loudly unless the result is `py3-none-any`: a platform tag means the build hit the C++ backend (wrong ref or packaging), which is the anti-silent-skip gate |
| Cpp wheel build env | The **runtime:v1** image — the runtime image built with `--no-flaggems`, tagged `{version}-build`. Its venv already has torch + deps + compilers, so `pip wheel ./cpp` just works: build env == delivery env, the same reason the vllm-plugin-FL native wheel builds in the runtime image |
| Cpp matrix | Only backends whose `configs.yaml` row sets `cmake_backend`. `cpp_matrix.py` filters `generate_matrix.py` output to those rows; `VENDOR_MAP` (CUDA→cuda, NPU→npu, GCU→gcu, IX→ix, MUSA→musa) turns `cmake_backend` into the `tools/set_cpp_vendor.sh` arg and the wheel's name token |
| Cpp distribution | One distribution per cmake backend (`flag_gems_cpp_cuda`, `_npu`, `_musa`, …), not per vendor — the same reason the flagcx wheel is one-per-backend: the library differs by backend family, and the name is what keeps them from colliding |
| Upload targets | The python wheel is identical everywhere, so release uploads the **same** `py3-none-any` wheel to every vendor PyPI **and** the daily index; the cpp wheel is per-vendor, so it goes only to `flagos-pypi-<vendor>` |
| Daily vs release | Daily → `flagos-pypi-daily` only. Release → every vendor index **plus** daily, because a freshly-pushed tag makes the daily build produce a clean release version, so the daily index would otherwise lack that exact version until the next commit |
| Deb ownership | The `packaging/debian/` definition is **upstream's** (already merged in FlagGems) and stays there — that is where distribution maintainers expect to find it. build-infra owns only the *release path* (clone → build → verify → publish), so producing packages does not depend on changes landing in the component repo. `Architecture: all` (pure Python), so it is published into every suite |
| Deb version duality | The `.deb` carries **two** versions that must agree: the changelog's (what apt sees) and the wheel's (what setuptools_scm writes into `dist-info` and `_version.py`). The build derives the wheel version from the stamped changelog (`5.4.0~rc2.post4-1 → 5.4.0rc2.post4` — Debian `~` is PEP 440 ``), passes it as `--build-arg FLAGGEMS_VERSION` → `SETUPTOOLS_SCM_PRETEND_VERSION` (pretend is fine here: the deb build context has no `.git`), then reads both back out of the installed package and fails on mismatch |
| Deb build env | `docker build` from upstream's `Dockerfile.deb`, `--network=host`, targeting `deb-output`. The published `5.4.0~rc2.post4` once held a `5.3.5` wheel because upstream's helper passed no `--build-arg` — the release path builds here with it, and gates on the `ARG` existing |

## Not here

- The FlagGems source itself, and its `packaging/debian/` definition — both upstream.
  build-infra clones a ref and overlays nothing (unlike flagcx, which overlays its own
  `debian/` directory).

## See also

- `packaging/flaggems/README.md` — how to run the build, what each workflow input means.
- `packaging/flaggems/build.sh` — the python-wheel build (clone → stamp → `pip wheel` → gate).
- `scripts/release_flaggems.py` — the release path: `build-python` / `upload-python` /
  `build-cpp` / `upload-cpp` / `update-config`.
- `scripts/cpp_matrix.py` — which backends build a cpp wheel (rows with `cmake_backend`).
- `.github/workflows/flaggems-wheel.yml` (daily), `flaggems-release.yml` (release),
  `flaggems-deb.yml` (deb release path).
- Docs site: Design → FlagGems (operator summary, links back here).
