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

The wheel line builds in the row's `wheel_base_image`. Some rows' runtime images carry no device
toolchain at all — the two nvidia rows have no nvcc, no `cuda_runtime.h`, no `nccl.h` and no
clang — and some rows' wheels must link at most glibc 2.35, which a 24.04 runtime cannot produce.
For those rows the builder channel publishes an image that can be the wheel build's `BASE_IMAGE`.
It is **self-contained on ubuntu:22.04**: it installs its own interpreter and torch pin and the
row's SDK, rather than layering on the runtime image. The 22.04 base is what lowers the wheel's
glibc floor to 2.35 — the reason a wheel built here installs on physical 22.04 hosts, not only
in 24.04 containers.

```bash
packaging/flagcx/build-flagcx-builder.sh --list
packaging/flagcx/build-flagcx-builder.sh --backend nvidia-cuda13.3
packaging/flagcx/build-flagcx-builder.sh --backend hygon-dtk26.04
packaging/flagcx/verify/verify-flagcx-builder.sh --backend nvidia-cuda13.3 --ref <sha>
packaging/flagcx/verify/verify-flagcx-builder.sh --backend hygon-dtk26.04
```

Only rows with a `builder:` block have one, and they declare it for two different reasons. The
nvidia rows need the toolchain the runtime lacks — so their recipe (`Containerfile.builder`) adds
the SDK apt packages, NCCL and clang/llvm 22 — while a vendor-SDK row such as hygon or ascend needs
only the floor: its runtime image already carries the toolchain but is 24.04, so its own recipe
(`Containerfile.builder-vendor-hygon` / `Containerfile.builder-vendor-ascend`, named by
`builder.containerfile`) installs the same SDK tarball and interpreter but no clang, bitcode or
NCCL. A row whose runtime image already carries the toolchain and whose wheel need not drop its
glibc floor builds straight from the runtime image and has none, which is the ordinary state and
not drift.

The verification is the acceptance test, not the image existing. `verify-flagcx-builder.sh`
compiles that row's device bitcode inside the built image and asserts the artifact: which
comm-traits branch it landed in (the two differ by a factor of seven in size), that it is
`nvptx64-nvidia-cuda` bitcode, and that the wrapper header came with it — or, on a vendor row
(which publishes no bitcode), imports the pinned torch against the SDK the image carries, which
is the step the wheel build stands in for. In CI, `.github/workflows/flagcx-builder.yml` runs that
before pushing. Nothing goes stale the way the runtime-based builder did — a self-contained image
records no runtime digest — and the glibc floor the wheel carries is asserted at the artifact, by
the `.so` gate in `wheel-build-in-container.sh`, not remembered here as an image digest.

The three rows are built, verified and published; the nvidia acceptance test was run on h20
against `21f8b5f`, the hygon one on hygon25:

| Row | At | Acceptance |
|---|---|---|
| `nvidia-cuda13.3` | h20 | clang 22, `sm_120`, CCL branch — 2,021,740 B of bitcode |
| `nvidia-cuda12.8` | h20 | clang 22, `sm_90`, Default branch — 274,820 B |
| `hygon-dtk26.04` | hygon25 | torch 2.9.0+das.opt1.dtk2604 imports against DTK 26.04 (no bitcode) |

The two sizes are the band's calibration as well as the record: the CCL branch pulls in
`nccl_device`'s device-side implementation, which is what separates them by a factor of seven, and
the numbers do not move with the compiler.

## Wheels

One wheel per backend, built in the backend's runtime image — or, on a row that publishes a builder
image, in that image instead (the nvidia rows, which have no clang; hygon, whose wheel needs the
22.04 floor).

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

The ref a build is made from is stated per dispatch, and it is what decides that version: a release
tag makes the wheel `<the tag's version>+<row label>`, and a branch makes it a `.dev<distance>` build
whose version only the build knows. `publish=true` therefore takes a tag as it stands and needs
`wheel_version` typed for anything else.

`import flagcx` also binds to the torch the wheel was built against — the extension leaves
`c10d::Work`'s virtuals to the loader, and one of them first exists in torch 2.9.0, so an older
torch fails at the import with an undefined symbol rather than at install. `WHEEL-DESIGN.md` has the
measurement. A consumer that wants only the bitcode can locate the package with
`importlib.util.find_spec` and never import it, which is the intended route.

### State

Enablement is a field per row in `backends.yaml` (`wheel.enabled`), and all twenty rows carry it —
so the two columns here are what has actually run, and they answer different questions. **Built +
verified** is the wheel installed from the file alone into a container of the row's runtime image,
on the row's own node, by the CI verify job unless the entry says otherwise. **Published** is the
pin the vendor index serves, which is the only column a user's `pip install` can see.

| Row | Built + verified | Published |
|---|---|---|
| `ascend-cann8.5.0` | 2026-10-19 | `0.14.0+cann8.5.0` |
| `ascend-cann8.5.0-910c` | 2026-10-19 | `0.14.0+cann8.5.0.910c` |
| `ascend-cann9.0.0` | 2026-10-19 | `0.14.0+cann9.0.0` |
| `ascend-cann9.0.0-910c` | 2026-10-19 | `0.14.0+cann9.0.0.910c` |
| `cambricon-neuware4.4.3` | 2026-10-09 | `0.14.0+neuware4.4.3` |
| `cambricon-neuware4.7.2` | 2026-10-17 | `0.14.0+neuware4.7.2` |
| `enflame-tops1.9.10` | 2026-10-18 | `0.14.0+tops1.9.10` |
| `enflame-tops1.10.6` | 2026-10-18 | `0.14.0+tops1.10.6` |
| `hygon-dtk26.04` | 2026-10-17 | `0.14.0+dtk2604` |
| `iluvatar-corex4.4.0` | 2026-10-18 | `0.14.0+corex4.4.0` |
| `iluvatar-corex4.5.0` | 2026-10-18 | `0.14.0+corex4.5.0` |
| `kunlunxin-xre5.37.1` | 2026-10-09 | `0.14.0+xre5.37.1` |
| `metax-maca3.7.2.1` | 2026-10-18 | `0.14.0+maca3.7.2.1` |
| `metax-maca3.8.1.3` | 2026-10-18 | `0.14.0+maca3.8.1.3` |
| `mthreads-musa4.3.6` | 2026-10-09 | `0.14.0+musa4.3.6` |
| `mthreads-musa5.2.0` | 2026-10-09 | `0.14.0+musa5.2.0` |
| `nvidia-cuda12.8` | 2026-10-17 | `0.14.0+cuda12.8` |
| `nvidia-cuda13.3` | 2026-10-17 | `0.14.0+cuda13.3` |
| `sunrise-tangrt1.2.0` | 2026-10-19 | `0.14.0+tangrt1.2.0` |
| `tsingmicro-tsm260610` | 2026-10-20 | `0.14.0+tsm260610` |

Every published pin is a build off the release tag `v0.14.0`, so the pins differ only in the row
label, and the pin is what tells two vendors' builds of one commit apart. All twenty rows were
built, verified and published off that tag; eighteen of them in a single dispatch on 2026-10-09,
and the two remaining ascend rows (`cann8.5.0`, `cann9.0.0`) finished on 2026-10-10 after the
publish-only failures on their nodes (the docker `~/.docker/config.json` proxies stale `noProxy`
left tencent/PyPI on the proxy path, which answered CONNECT 500; removing the proxies entry let
those nodes reach the tencent mirror directly). The two nvidia pins were re-published on
2026-10-17 after the wheel moved onto the self-contained 22.04 builder (PR #1372, and the bundle
smoke flip back to 22.04 in PR #1376) — same pins, now 22.04-clean — which is why their date
differs from the original dispatch. hygon's pin was re-published on 2026-10-17 after
its wheel moved onto the 22.04 builder (PR #1380) — same pin, now 22.04-clean — which is why its
date differs from the other nineteen. cambricon-neuware4.7.2's pin was re-published the same way
on 2026-10-17, off its own 22.04 builder (PR #1389) — same pin, now 22.04-clean. The two metax pins
were re-published on 2026-10-18 off the shared metax 22.04 builder (PR #1394) — same pins, now
22.04-clean. The two enflame pins were re-published the same way on 2026-10-18, off the shared
enflame 22.04 builder (PR #1398) — same pins, now 22.04-clean (max GLIBC_2.34, no forbidden
symbols). The two iluvatar pins were re-published the same way, off the shared iluvatar 22.04
builder, on the same day — same pins, now 22.04-clean. The four ascend pins were re-published the
same way on 2026-10-19, off the shared `Containerfile.builder-vendor-ascend` 22.04 builder — same
pins, now 22.04-clean (max GLIBC_2.34, no forbidden symbols); 910b and 910c of one CANN version
still build the same wheel bytes, only the label differs. The sunrise pin was re-published the same
way on 2026-10-19, off its own `Containerfile.builder-vendor-sunrise` 22.04 builder (PR #1418) —
same pin, now 22.04-clean (`_C*.so` max GLIBC_2.32, `libflagcx.so` GLIBC_2.34, no forbidden
symbols); its SDK-floor proof is a dlopen of libpccl/libtangrt_shared rather than the bridge import,
because torch-ptpu probes the device in a constructor and aborts device-less. The tsingmicro pin was
re-published the same way on 2026-10-20, off its own `Containerfile.builder-vendor-tsm` 22.04 builder
(PR #1422) — same pin, now 22.04-clean (`_C*.so` max GLIBC_2.32, `libflagcx.so` GLIBC_2.34, no
forbidden symbols); its SDK-floor proof is `import txops` plus a dlopen of libhpgr/libtccl rather
than `import torch_txda`, whose TXDAHooks constructor probes the device and aborts device-less. The release re-publish builds with
`bitcode=false`: iluvatar's `bindings/ir` Makefile (FlagCX #668) is not in the `v0.14.0` tag, so a
release wheel carries no `libflagcx_device.bc`; the bitcode ships in the daily dev-pin build off
`main`, which is what the `bitcode` input defaults to `true` for (see `--no-bitcode` in
build-flagcx-wheel.sh). A `main` build is versioned `0.15.0.dev<distance>+<label>.<date>.<node>`
and published to `flagos-pypi-iluvatar` with `wheel_version` typed, one row per dispatch — the
dev pin's date/node moves with `main`, so it is re-derived each time rather than recorded here.

`kunlunxin-xre5.37.1` carries a CI record now (2026-09-22); before that the row had passed only on
the node, while the wheel channel was being enabled for it (#1000).

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
| `Containerfile.wheel` | the wheel build's environment, on the backend's runtime image — or on its builder image where the row has one; it prepares (SDK assert, build-only headers, interpreter probe, clone), it does not compile |
| `wheel-build-in-container.sh` | the compiling half: exec'd in a container from that image, carrying the row's device flags |
| `build-flagcx-wheel.sh` | the wheel line's entry point; `--print-pin` reads a built wheel |
| `Containerfile.builder` | the build-toolchain image, on top of the runtime image |
| `build-flagcx-builder.sh` | the builder line's entry point; tags the published ref |
| `verify/` | `verify-flagcx-deb.sh` installs the `.deb` into its base image and a plain Ubuntu; `verify-flagcx-wheel.sh` installs the wheel from the file or from the index; `verify-flagcx-builder.sh` compiles the row's device bitcode in the builder image |

`debian/control` is **generated** — edit `control.in`, never the rendered file.
