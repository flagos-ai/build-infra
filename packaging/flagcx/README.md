# FlagCX packaging

Builds FlagCX out of a git ref, one backend per container. Three channels share one
`backends.yaml`, one join (`flagcx-config.py --channel …`) and one set of registry facts:

| Channel | Product | Design of record |
|---|---|---|
| `deb` (default) | `libflagcx-<backend>` / `-dev` `.deb` pairs | `DESIGN.md` |
| `wheel` | Python wheels for the vendor PyPI | `WHEEL-DESIGN.md` |
| `builder` | build-toolchain images, `flagos-dev/flagcx-builder-<backend>` | `WHEEL-DESIGN.md` |

**`DESIGN.md` is the design of record** — why the packages look the way they do, and what each
`backends.yaml` field is for. This file is only how to run it.

## Quickstart

```bash
packaging/flagcx/build-flagcx-deb.sh --list                  # ready vs probe-pending
packaging/flagcx/build-flagcx-deb.sh --backend metax-maca3.8.1.3 \
    --ref v0.14.0-rc1.post1 --out /tmp/dist
packaging/flagcx/verify/verify-flagcx-deb.sh --backend metax-maca3.8.1.3 \
    --floor-image ubuntu:24.04 /tmp/dist/*.deb
```

`--ref` is not defaulted to a branch on purpose. With `--src DIR` instead, the script reads the
tag `DIR`'s HEAD sits on and warns when it has to fall back to a branch — a `.deb` is a release
artifact, so an unreproducible one is worth saying out loud.

In CI the same recipe runs through `.github/workflows/flagcx-deb.yml` (manual dispatch), which
builds one backend per runner and then verifies before uploading. With `publish: true` (and
therefore `verify: true`) the verified `.deb` is pushed to the apt repo named for the Ubuntu
release its base image was built on — `flagos-apt-ubuntu24.04` or `flagos-apt-ubuntu22.04` —
so a user adds the repo matching their distro and never has to know a glibc floor exists.
A last step then reads that repository back the way a user does, installing by package name and
checking the version that lands: a `curl` returning 0 says the artifact was accepted, not that
the index a client reads is right.

Adding the repo is therefore all a user does — the key the repository is signed with goes to
`/usr/share/keyrings/`, and the suite is the distro's own codename:

```bash
# <backend> is the vendor/backend the package was built for, e.g. nvidia-cuda12.8
sudo install -D -m 0644 flagos-apt.asc /usr/share/keyrings/flagos-apt.asc
echo "deb [signed-by=/usr/share/keyrings/flagos-apt.asc] \
https://resource.flagos.net/repository/flagos-apt-ubuntu24.04 noble main" \
  | sudo tee /etc/apt/sources.list.d/flagos.list
sudo apt-get update && sudo apt-get install libflagcx-<backend>
```

On 22.04 the repo is `flagos-apt-ubuntu22.04` and the suite is `jammy`. The suite is not a free
choice: apt takes it as a literal path (`dists/<suite>/Release`), and a repo serving `noble`
does not answer a client asking for `Noble`.

Every build needs a Docker host that can reach the registry and pull the backend's base image.
The build itself takes the base image as-is and adds only `debhelper`/`fakeroot`/`devscripts`
plus the backend's `apt:` packages — no runtime image is involved.

## Builder images

Some rows' runtime images carry no device toolchain at all — the two nvidia rows have no nvcc, no
`cuda_runtime.h`, no `nccl.h` and no clang — and the wheel line builds *in* the runtime image. For
those rows the builder channel publishes an image that can be the wheel build's `BASE_IMAGE`: the
runtime image plus the row's own SDK packages, `builder.apt`, and clang/llvm 22.

```bash
packaging/flagcx/build-flagcx-builder.sh --list
packaging/flagcx/build-flagcx-builder.sh --backend nvidia-cuda13.3
packaging/flagcx/verify/verify-flagcx-builder.sh --backend nvidia-cuda13.3 --ref <sha>
```

Only rows with a `builder:` block have one. A row whose runtime image already carries what the
build needs — every vendor-SDK row, whose base image brings the toolchain with it — builds its
wheel straight from the runtime image and has none, which is the ordinary state and not drift.
The image is arch-agnostic: `bitcode_arch` is the arch the verification compiles at, not a
property of the image.

The verification is the acceptance test, not the image existing. `verify-flagcx-builder.sh`
compiles that row's device bitcode inside the built image and asserts the artifact: which
comm-traits branch it landed in (the two differ by a factor of seven in size), that it is
`nvptx64-nvidia-cuda` bitcode, and that the wrapper header came with it. In CI,
`.github/workflows/flagcx-builder.yml` runs that before pushing, and the image is stale whenever
the runtime image it was built on has been rebuilt — `flagos.base_digest` records which one that
was, so the staleness is detectable rather than remembered.

Both rows are built, verified and published; the acceptance test was run on h20 against `21f8b5f`:

| Row | At | Acceptance |
|---|---|---|
| `nvidia-cuda13.3` | h20 | clang 22, `sm_120`, CCL branch — 2,021,740 B of bitcode |
| `nvidia-cuda12.8` | h20 | clang 22, `sm_90`, Default branch — 274,820 B |

The two sizes are the band's calibration as well as the record: the CCL branch pulls in
`nccl_device`'s device-side implementation, which is what separates them by a factor of seven, and
the numbers do not move with the compiler.

## Wheels

One wheel per backend, built in the backend's runtime image — or, on a row that publishes a builder
image, in that image instead, because the runtime image has no clang.

```bash
packaging/flagcx/build-flagcx-wheel.sh --list
packaging/flagcx/build-flagcx-wheel.sh --backend nvidia-cuda13.3 --ref <sha> --out dist/
packaging/flagcx/build-flagcx-wheel.sh --print-pin dist/flagcx-*.whl
packaging/flagcx/verify/verify-flagcx-wheel.sh --backend nvidia-cuda13.3 --wheel dist/flagcx-*.whl
```

Every wheel carries `flagcx/lib/libflagcx.so`, the `_C` extension and `flagcx/api.py`. A row that
states `bitcode_arch` carries two more — `flagcx/lib/libflagcx_device.bc` and the headers under
`flagcx/include/` — compiled by the build image's clang and packaged by FlagCX's own `setup.py`
([#614](https://github.com/flagos-ai/FlagCX/pull/614), from `v0.14.0-rc2.post2`), which the line
hands the row's `bitcode_arch` and `bitcode_adaptor_flag` as `FLAGCX_BITCODE_ARCH` and
`FLAGCX_BITCODE_ADAPTOR_FLAGS`. `WHEEL-DESIGN.md` says what each file is for and why the paths are
the ones they are.

The install contract is the exact pin (`pip install 'flagcx==<version>+<label>'`); a range is
satisfied by every vendor's build of the same commit, so nothing else can tell them apart.

Both rows are built and verified locally; the acceptance test is the wheel installed into a
container of the row's runtime image, run on h20 against `21f8b5f` — and neither is published to
an index yet:

| Row | Pin | Acceptance |
|---|---|---|
| `nvidia-cuda13.3` | `0.14.0rc2.post2.dev1+cuda13.3.20260920.g21f8b5f` | installs and imports; `sm_120`, 2,021,740 B of bitcode |
| `nvidia-cuda12.8` | `0.14.0rc2.post2.dev1+cuda12.8.20260920.g21f8b5f` | installs and imports; `sm_90`, 274,820 B |

## Adding a backend

1. Add an entry to `backends.yaml` under either the `ready` or `probe-pending` heading, with a
   `probe:` note saying what one in-container `make` + `ldd` still has to answer.
2. Run `python3 packaging/flagcx/flagcx-config.py --check` — it cross-checks the entry against the
   runtime matrix (base image, arch, glibc floor) and fails with a named reason on drift.
3. Build and verify it. **A probe-pending entry is only flipped to `enabled: true` after that
   build and verify pass** — the `probe:` note is deleted, not resolved on paper.
4. Give the vendor exactly one `deb.default_for_vendor: true`, which is the variant carrying
   `Provides: libflagcx-<vendor>`.

Two fields are the usual reason a first build fails, and neither is guessable from the
Makefile: `make_env` (the FlagCX Makefile's `?=` ladders are pre-assigned, so a vendor `.mk`
default is unreachable and an unset variable silently becomes an empty path) and
`vendor_lib_dirs` (a vendor soname the loader cannot see at all is a hard `dpkg-shlibdeps`
error, and nothing else in the build knows where it lives). `DESIGN.md` has the details.

A row whose runtime image lacks what the FlagCX build needs additionally gets a `builder:` block
and the two `bitcode_*` fields that state how its device bitcode is compiled — those are what the
builder channel's verification rebuilds. Everything else on that channel is a field the row
already states.

## Verified

A row means the applicable tests in `DESIGN.md` §Verification passed on the vendor's own node:
the `.deb` installs into its matching base image and its soname resolves with the vendor symbols
bound (`smoke-load` under `RTLD_NOW`), **and** `apt-get install` exits 0 in a plain Ubuntu at the
package's libc6 floor. The third test — installing from the published repository — applies only
once a package has been published, which no row here has been yet.

| Backend | Where | Result |
|---|---|---|
| `nvidia-cuda12.8` | h20 | full + floor pass, `smoke-load` under `RTLD_NOW` passes |
| `nvidia-cuda12.8` negative test | h20 | dropping `libnccl-dev` aborts at the `assert` instead of shipping a collector-less `.so` |
| `ascend-cann9.0.0-910c` | hw115 (aarch64) | build + verify pass — exercises the arm64 stanza |
| `enflame-tops1.9.10`, `enflame-tops1.10.6` | enflame node | build + verify pass at `v0.14.0-rc1.post2` |

The enflame rows are pinned to `v0.14.0-rc1.post2` because it is the first tag carrying the
`topsDeviceProp_t` fix ([FlagCX #580](https://github.com/flagos-ai/FlagCX/pull/580)); an
enflame build from an earlier ref fails to compile, so there is no honest earlier row to record.

## Layout

| Path | What |
|---|---|
| `DESIGN.md` | design of record — rationale, `dpkg-shlibdeps` mechanism, ADRs |
| `WHEEL-DESIGN.md` | design of record for the wheel and builder lines — identity, version label, pin |
| `backends.yaml` | per-backend packaging facts: the one input build-infra cannot derive |
| `flagcx-config.py` | joins `backends.yaml` with `generate_matrix.py --runtime` |
| `Containerfile.deb` | the deb build, on top of the backend's base image |
| `debian/` | `rules` + `control.in`; `debian/control` is rendered on the host |
| `build-flagcx-deb.sh` | local/CI entry point, one backend per invocation |
| `Containerfile.wheel` | the wheel build, in the backend's runtime image — or in its builder image where the row has one |
| `build-flagcx-wheel.sh` | the wheel line's entry point; `--print-pin` reads a built wheel |
| `Containerfile.builder` | the build-toolchain image, on top of the runtime image |
| `build-flagcx-builder.sh` | the builder line's entry point; tags the published ref |
| `verify/` | `verify-flagcx-deb.sh` installs the `.deb` into its base image and a plain Ubuntu; `verify-flagcx-wheel.sh` installs the wheel from the file or from the index; `verify-flagcx-builder.sh` compiles the row's device bitcode in the builder image |

`debian/control` is **generated** — edit `control.in`, never the rendered file.
