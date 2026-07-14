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
# from a ref (default: wheel-packaging-split — see note below)
FLAGGEMS_REF=wheel-packaging-split ./build.sh

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

## ⚠️ Temporary: FlagGems ref

`FLAGGEMS_REF` defaults to the **under-review `wheel-packaging-split` branch**,
which carries the pure-Python setuptools packaging (`build-backend =
setuptools.build_meta`). On the FlagGems default branch today, `pip wheel .`
still uses scikit-build and tries to compile C++.

**Once `wheel-packaging-split` merges, change the default ref to the FlagGems
default branch** (in `build.sh` and the workflow) and delete this note.
