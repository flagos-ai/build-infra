# FlagCX deb packages — design

Status: **design of record, not yet implemented.** The operator-facing `README.md` for this
line (how to run the build, `backends.yaml` field meanings) is written alongside the code.

Goal: make FlagCX installable as a `.deb` on **every backend build-infra can build an image
for**, instead of the two it ships today.

## Context

build-infra builds base + runtime images for **20 backends across 11 vendors**, and FlagCX
has a working `makefiles/<backend>.mk` plus a `USE_*_ADAPTOR`-guarded CCL adaptor for
essentially every one of them. What FlagCX ships today is installable packages for exactly
**two**: `nvidia` and `metax`, via a hand-enumerated flow (a `Package:` stanza per vendor,
an `ifeq` ladder in `rules`, a two-arm `case` in `build-flagcx.sh`, a hardcoded
`for vendor in nvidia metax` upload loop). The library *can* be built for those backends;
it just cannot be *shipped* for them.

**The packaging solution lives in `build-infra`, under `packaging/flagcx/`.** The FlagCX
repository is **not touched at all this round** — the new line is self-contained: it clones
FlagCX at a pinned ref into a build container and overlays its own `debian/` directory on
top. Only the deb format is in scope; RPM is deferred and the FlagCX repo's own
`packaging/rpm/` flow stays as it is. (Paths written `packaging/<x>/` below without a
`build-infra` qualifier are FlagCX-repo paths; build-infra has no `packaging/rpm/`.)

### Decisions taken

| Question | Decision |
|---|---|
| Home | `build-infra/packaging/flagcx/` — self-contained, zero FlagCX changes |
| Scope | All 20 buildable backends, including `nvidia` and `metax` |
| Format | **deb only this round.** RPM deferred and untouched |
| Build environment | build-infra **base** images (runtime `/ -build` images only if a base proves insufficient) |
| Existing FlagCX deb flow | Superseded by this path. Retiring `build-deb.yml` / `upload-nexus.yml` is a **later, separate FlagCX PR** — both producers coexist harmlessly this round because nothing is published |
| Package naming | Per-backend `libflagcx-<backend-key>` + `-dev`, with `Provides: libflagcx-<vendor>` on the one `default_for_vendor` variant |
| Version scheme | Fix now: derive from the git tag, mapping `-rcN` → `~rcN` so pre-releases sort **below** the release |
| CI verification | Per-backend build + **in-container install + dlopen**. No hardware smoke test |
| Publication | Deferred — the apt repository is not chosen yet |

### Two latent defects this path removes

Both found reading the current flow:

- The changelog's newest entry `0.13.0-rc0.1-1` sorts **above** the real `0.13.0` (a version
  string ends as *less* than any character), so an rc can never be superseded by its own
  release.
- `libflagcx.so.0.1.0` is a bogus symlink to the unversioned real file, so `dh_makeshlibs`
  records nothing sensible.

### Two facts that shape the design

- **The publisher already exists and is reusable.** `.github/workflows/upload-nexus.yml`
  is `workflow_call` (input `run_id`, secret `NEXUS_TOKEN`) and posts to
  `NEXUS_APT_URL=https://resource.flagos.net/repository/flagos-apt-hosted`. It downloads
  artifacts from a sibling workflow **hardcoded to the name `build-deb.yml`** and lands them
  in `packages/`. So when publication is switched on later, the build workflow needs to be
  named `build-deb.yml` (or the publisher generalized) — the only real work left.
- **Reuse `scripts/generate_matrix.py`, do not write a new generator.** Its `--runtime`
  output already carries everything a deb build needs per backend: `name`, `runson`,
  `version`, `base_image`. build-infra's own convention (`scripts/README.md`) is that a
  packaging line adds *scripts*, not matrix generators.

## Line shape

`flagcx` is a **non-app packaging line** — the same class as `packaging/flash-attn/` (one
Containerfile + README) and `packaging/megatron/builder/` (clone-from-git, in-image build,
artifact extract). It is explicitly *not* the four-app skeleton in `packaging/README.md`, so
it gets a single root `README.md` as its entry point rather than a `docs/` tree.

```
packaging/flagcx/
  DESIGN.md                  # this file
  README.md                  # operator entry point (written with the code)
  debian/                    # overlay, copied into the cloned FlagCX tree
    control.in               # template; rendered per backend
    rules                    # ~30 lines, no if/else, no vendor ladder
    changelog.sh             # generates debian/changelog from the clone's git tags
    patch-soname.sh          # SONAME + rpath normalization
    source/format            # "3.0 (quilt)" — dpkg-buildpackage wants it declared
  Containerfile.deb          # BASE_IMAGE + BACKEND + FLAGCX_REF -> /output/*.deb
  build-flagcx-deb.sh        # --backend KEY... | --all | --list
  deb-config.py              # merges backends.yaml with generate_matrix --runtime
  backends.yaml              # FlagCX-owned facts, one entry per backend key
  verify/verify-flagcx-deb.sh
  verify/smoke-load.c

FlagCX repo:  unchanged this round
```

## Design

### 1. `backends.yaml` — FlagCX-owned facts only

Hand-written, one entry per backend keyed by the build-infra `{vendor}-{backend}` name.
What build-infra already knows (`base_image`, `runson`, `version`) is **not** duplicated
here — it comes from `generate_matrix.py --runtime` at build time. `arch` and `glibc_floor`
**are** here, because `--runtime` carries neither: it emits no arch field at all, and the
glibc floor is a packaging decision even though `--check` cross-checks it against the base
image's own Ubuntu release.

```yaml
nvidia-cuda12.8:
  vendor: nvidia
  arch: amd64
  glibc_floor: "2.39"                  # the base's Ubuntu 24.04; 22.04 bases carry "2.35"
  make_flag: USE_NVIDIA                # from plugin/torch/_build_config.py ADAPTOR_TO_MAKE_FLAG
  apt: [cuda-nvcc-12-8, libnccl-dev]   # on top of the base image
  make_env: {DEVICE_HOME: /usr/local/cuda, CCL_HOME: /usr}
  vendor_libs: [cuda, cudart, nccl]    # the vendor libs dh_shlibdeps must not try to resolve
  assert: [/usr/include/nccl.h]
  deb: {enabled: true, default_for_vendor: true}
```

`apt`, `make_env`, `assert` and `vendor_libs` are exactly the fields the in-container path
probes below will fill in. Two facts already checked while grounding this design: every base
image carries `build-essential` (so `gcc`, `g++`, `make` and `dpkg-dev` are present), and
**none** carries `debhelper`, `fakeroot`, `devscripts` or `patchelf` — those are added by the
container, in one place.

### 2. `deb-config.py` — the join, and nothing else

`--merge <matrix.json>` reads `generate_matrix.py --runtime` output and `backends.yaml`,
emits the CI matrix (one entry per enabled backend, with the FlagCX fields joined in) and
per-backend build inputs. `--check` fails when `backends.yaml` names a backend that
`generate_matrix.py` does not consider buildable (or vice versa for enabled entries) — that
is the drift alarm between the two repos. Small enough to read in one sitting; it holds no
version logic and no build logic.

### 3. `.github/workflows/flagcx-deb.yml` — dispatch-only, build-infra conventions

`workflow_dispatch` only, with the standard `authorize` first job
(`./.github/actions/check-trigger-author`), action SHAs pinned with `# vN` comments, inputs
`backend` (default `all`), `flagcx_ref`, `verify` (default `true`). Jobs:

| Job | Shape |
|---|---|
| `set-matrix` | `generate_matrix.py --runtime` → `deb-config.py --merge` → `fromJSON` matrix; each row carries the `ubuntu` field the verify job needs for `--floor-image` |
| `build` | `runs-on: ${{ fromJSON(matrix.runson) }}`; `build-flagcx-deb.sh --backend <key>`; uploads the `.deb` files as artifacts |
| `verify` | `verify/verify-flagcx-deb.sh --backend <key> --floor-image ubuntu:<ubuntu>` on the downloaded `.deb` files |

`verify/verify-flagcx-deb.sh` installs the package and runs `smoke-load.c` (~15 lines:
`dlopen("libflagcx.so.0", RTLD_NOW)` — `RTLD_NOW` forces vendor-symbol resolution at load —
then `dlsym` + call `flagcxGetVersion` and `dlsym("flagcxCommInitRank")`), then `ldd` on the
installed `libflagcx.so.0`.

**Publication hook (deferred).** `upload-nexus.yml` waits on `build-deb.yml`; when a
repository is chosen, the mechanical options are (a) rename this workflow to `build-deb.yml`,
or (b) give the reusable publisher a `workflow` input. Nothing in the line's design blocks
either — the artifact is already a plain `.deb` set.

### 4. `Containerfile.deb`

Mirrors `packaging/flash-attn/Containerfile` + `packaging/megatron/builder/Containerfile`:
`ARG BASE_IMAGE` (from the matrix), `ARG FLAGCX_REPO` / `ARG FLAGCX_REF`, `ARG BACKEND`, and
the four host-resolved build inputs `DEB_APT`, `DEB_ASSERT`, `DEB_MAKE_FLAG`, `DEB_MAKE_ENV`.
Then, in order: the unconditional deb-toolchain install (`build-essential debhelper fakeroot
devscripts patchelf git ca-certificates` — none of which a vendor base ships), the `DEB_APT`
install and the `DEB_ASSERT` file gate, an 8-attempt retry clone (**`--recurse-submodules
--shallow-submodules`** — `Makefile:245` defaults `JSON_INCLUDE_DIR` to
`third-party/json/single_include`, and no base image has `nlohmann-json3-dev`), the
mtime-less overlay copy of `packaging/flagcx/debian/` into the tree, `debian/changelog.sh`,
then `dpkg-buildpackage -us -uc -b`.

`debian/control` is **not** rendered in the container: the runtime matrix is a build-infra
fact that does not exist inside a base image, so the host renders it and the overlay `COPY`
carries it in. `DEB_MAKE_FLAG` / `DEB_MAKE_ENV` are re-passed as environment for
`dpkg-buildpackage`, since a build `ARG` is not an environment variable and `debian/rules`
reads them from the environment.

**Single stage**, like both precedents — the artifacts are read out of the image rather than
copied to a later stage, so there is no `--target output`. Extraction is the
`docker create` / `docker cp <cid>:/output/.` / `docker rm` pair, as in `packaging/flagtree`
and `packaging/megatron`. The final `RUN` asserts with `dpkg-deb -c` that both packages
landed and that each carries what it claims: the versioned `libflagcx.so.*` in the runtime
package, headers and the unversioned linker symlink in `-dev`.

`HTTPS_PROXY` is an `ARG` with an empty default, exported inside the clone `RUN` only —
never an image `ENV`, because a baked proxy is a leaked proxy.

The build runs with **`--network host`**. The clone is the only thing in it that needs the
network, and the default bridge on the runners intermittently cannot open a TCP connection to
github.com while the host can: measured on metax124, 1 of 2 bridge clones died at connect after
130 s and 2 of 2 host clones finished in 12 s. Container isolation buys nothing for a build that
has to reach GitHub anyway, and it costs an 8-attempt retry loop that can spend 17 minutes
failing.

Pinned-ref discipline: `FLAGCX_REF` defaults to a **tag**, not `main`, so an artifact is
reproducible. `FLAGCX_REPO` is an `ARG` so a filestore tarball can replace the clone later if
github.com proves unreachable from the runners — the same escape hatch `packaging/vllm/` uses.

### 5. `debian/` overlay

**`control.in`** — one binary-package stanza per package, rendered per backend, carrying
`Architecture:` (arm64 for the 4 Ascend CANN backends, amd64 for the other 16),
`Depends: libc6 (>= <floor>)` (glibc 2.39 for the 16 Ubuntu 24.04 bases, 2.35 for the 4
Ubuntu 22.04 ones), and provenance fields `X-FlagCX-Build-Image` / `X-FlagCX-Backend` /
`X-FlagCX-Build-Infra-Version`.

The relationship fields name packages, so they are the ones worth spelling out:

- `Provides: libflagcx-<vendor>` — on the one `default_for_vendor` variant, which is the only
  variant that answers to the unqualified name.
- `Conflicts:` — the *same-arch* siblings, unversioned, comma-separated. Two variants of one
  vendor cannot coexist, and neither can two vendors.
- `Replaces: libflagcx-<vendor> (<< ${binary:Version})` (dev: `libflagcx-<vendor>-dev`),
  gated on the same `default_for_vendor` flag as `Provides`. It is versioned and it is
  `Replaces`, never `Breaks`: nothing here conflicts on a file path — the legacy packages
  install under `/usr/local`, ours under `/usr`.

A versioned relation is one atom, so `Replaces:` and its siblings are comma-separated while
`Conflicts: a b` (space only) would not be valid control syntax. `--build-inputs` emits these
fields already in control syntax and the renderer only collapses whitespace — splitting them
into tokens is what once turned `libflagcx-nvidia (<< ${binary:Version})` into three bogus
packages.

`X-FlagCX-Build-Infra-Version` is read from the **matrix** row's `version`, not from a field
in `backends.yaml`: the packaging is part of the stack release, and a version written down
twice goes stale silently.

**`rules`** — ~30 lines with no vendor ladder, and **no `Build-Profiles` machinery at all**:
one container builds one backend, so the generated `control` holds exactly one stanza set.
This deletes the 19-term negated profile lists (O(n²)) outright rather than inverting them.
It calls `make` with the registry's build inputs and overrides `dh_shlibdeps` to
`dh_shlibdeps -- --ignore-missing-info`, dropping today's `dh_shlibdeps ... || true`, which
swallows every dependency error. `--ignore-missing-info` and not `-X<lib>`: `-X` excludes by
*package* name, so it would also stop checking the vendor libs' own correctly-resolvable
dependencies, while `--ignore-missing-info` keeps every check the package should satisfy
(`libc6`, `libstdc++6`, `libgcc-s1`) and forgives only the ones no dpkg database can resolve.

`dh_dwz` is overridden to a no-op. It deduplicates DWARF across a package's binaries, and it is
the one step whose output is not shipped — `dh_strip` runs immediately after it. The Metax
linker interleaves allocatable and non-allocatable sections, which `dwz` refuses with
`Allocatable section ... after non-allocatable ones`, so on that toolchain the step can only
lose the build.

The registry's `make_flag` / `make_env` reach `make` as **command-line variables**
(`MAKE_ARGS := ... $(DEB_MAKE_ENV) $(DEB_MAKE_FLAG)=1`), which is what lets them outrank the
Makefile's own `ifeq` ladder. The ladder pre-assigns `DEVICE_HOME` / `CCL_HOME` *before*
including `makefiles/*.mk`, so each vendor `.mk`'s `?=` default is unreachable; an unset
environment variable therefore yields a *defined but empty* value, and `DEVICE_LIB :=
$(DEVICE_HOME)/lib64` silently becomes `/lib64`. A command-line variable outranks both the
`?=` and the ladder.

`debian/rules` guards `DEB_MAKE_FLAG` with a parse-time `$(error)` rather than trusting it to
arrive. It is not a variable dpkg knows, so `dpkg-buildpackage` is within its rights to sanitize
it away, and the loss is not self-describing: an empty value expands `$(DEB_MAKE_FLAG)=1` to a
bare `=1`, which `make` rejects as "empty variable name" without naming the variable or saying
why. The guard makes the first build say which input went missing.

Makefile knobs it relies on (verified in the FlagCX tree): `BUILDDIR` (`Makefile:4` — the real
knob; today's `debian/rules` uses the wrong name `BUILD_DIR_METAX`), `COMPILE_KERNEL ?= 0`
(`:26`, so no vendor device compiler is needed and plain g++ links), `DESTDIR ?= $(PREFIX)/lib`
(`:242`), `INC_DESTDIR` (`:243`, passed pre-namespaced as `.../usr/include/flagcx` because
`install:` is a flat `cp`), and the `DESTDIR` term in `clean:` (`:371`) — so `DESTDIR` is
always passed to clean.

**`changelog.sh`** — generates `debian/changelog` inside the container from the clone's own
tags (`git tag --sort=-creatordate` + `git log` between consecutive tags). Because the source
is a fresh clone, there is no committed changelog and therefore **no staleness gate** — that
whole risk category disappears. `vX.Y.Z` → `X.Y.Z-1`; `vX.Y.Z-rcN[.M][.postP]` →
`X.Y.Z~rcN[.M][.postP]-1`; unparseable → exit non-zero rather than guess.

**`patch-soname.sh`** — rename the built `libflagcx.so` to `libflagcx.so.<ver>`,
`patchelf --set-soname libflagcx.so.0`, `patchelf --remove-rpath` (the link line at
`Makefile:343` bakes `-Wl,-rpath` for `LIBDIR`/`CCL_LIB`/`HOST_CCL_LIB`/`UCX_LIB`), then the
`libflagcx.so.0 → .<ver>` runtime symlink and the `libflagcx.so → .<ver>` dev symlink. FlagCX's
Makefile has no `-soname` flag and stays untouched.

### 6. Backend triage

**12 backends ready immediately** (nvidia ×2, metax ×2, cambricon ×2, enflame ×2, ascend ×4):
their `makefiles/*.mk` defaults and the base-image SDK layout already agree.

**8 need one in-container path probe each** before `apt`/`make_env`/`assert` can be written:
`hygon-dtk26.04` (does DTK ship `nccl.h` + `libnccl.so`?), `iluvatar-corex4.4.0` and `4.5.0`
(corex lib dir on the link path), `kunlunxin-xre5.37.1` (`kunlunxin.mk`'s `DEVICE_LIB` is
`/usr/local/xpu/lib` but `-lcudart` lives in `/usr/local/xcudart/lib`), `mthreads-musa4.3.6`
and `5.2.0` (mccl layout under `/usr/local/musa`), `sunrise-tangrt1.2.0` (`sunrise.mk` defaults
`CCL_HOME=/usr/local/pccl` while the base installs tangrt's own tree),
`tsingmicro-tsm260610` (`-ltccl`/`-lhpgr` under `/usr/local/kuiper`), plus the enflame ECCL
header location. None is hard-blocked: `COMPILE_KERNEL=0` is already the default, so no vendor
device compiler is involved. Each probe is a `make` + `ldd` inside the base image.

**nvidia is the one under-provisioned build.** Its base is
`nvcr.io/nvidia/cuda:12.8.0-runtime-ubuntu24.04` — no nvcc, no NCCL, and build-infra provisions
NCCL for no vendor. `COMPILE_KERNEL=0` means no device compiler is needed, but `nvidia.mk`
resolves `CCL_INCLUDE` at make-parse time, so the headers must be there.
`apt: [cuda-nvcc-12-8, libnccl-dev]` first; if the CUDA apt repo is unreachable in the base,
fall back to the pip route already used by `packaging/rpm/dockerfiles/Dockerfile.rpm.nvidia`
(`nvidia-cuda-nvcc-cu12`, `nvidia-nccl-cu12`). The `assert` list makes the difference loud
instead of silent.

## Registration

Adding this line touches these surfaces, following `docs/agent-protocol.md` §4 (index is the
only entry point) and `packaging/README.md`'s 引用维护清单:

- `packaging/README.md` — add the `flagcx` row to 各 app 变体 and note it alongside the
  flagtree/flaggems/flash-attn exclusion (non-app line, plain `README.md` entry point).
- `packaging/flagcx/README.md` — the line's entry point: what it builds, how to run it, the
  `backends.yaml` field meanings, and the publication hook.
- `CLAUDE.md` — the layer table plus the `### CI workflows` list.
- `scripts/README.md` — only if `deb-config.py` ends up CI-referenced from `scripts/`; verify
  during implementation rather than assume.
- `license-tool` — `packaging/` is in `SKIP_PATH_PREFIXES`, so overlay files need no license
  header (same as every existing packaging line). Confirm with a scan, do not assume.

**Deferred, not forgotten:** no status matrix this round, because there is no on-node
verification. Registering one later is mechanical — `packaging/flagcx/status_matrix.*.yaml`
plus a row in `docs/status-matrix.md` and entries in `scripts/render_status_matrix.py`
(`COMPONENTS`, `APP_TYPES`, `BACKENDS`) and `scripts/verify_collect_cells.py` (`APP_VERIFY`).
`docs/agent-protocol.md` §6 (upstream PR URLs into `prs:`) does not bite this round, since no
PR to another repo is opened.

## Risks

1. `nvidia.mk` / `nvidia_gencode.mk` fail **silently** on a missing header or compiler rather
   than erroring. Mitigation: the registry `assert` list, run before the build, and a negative
   test that proves it fires.
2. `apt-get install` of the deb toolchain must reach a working mirror in 20 different base
   images, some of which are air-gapped vendor SDK images. Each image already does
   `apt-get install` at build time, so this should hold — but it is unverified for the
   `-910c`/vendor-only images and is the likeliest first failure.
3. Two glibc floors (2.39 / 2.35) and two arches land in one eventual APT repo. Mitigation:
   per-stanza `Architecture:` + `Depends: libc6 (>= floor)`, and verify in the same base image
   the package was built in.
4. build-infra base tags are **mutable** and nothing is pinned by digest anywhere in the repo.
   Record the base image ref plus the resolved digest in `X-FlagCX-Build-Image` so a package is
   traceable to the image that produced it.
5. `COMPILE_KERNEL=1` (opt-in, unused here) switches the linker for hygon (`Makefile:336`) and
   would need vendor compilers elsewhere — out of scope.
6. Four Ascend entries produce two content-identical pairs (the `-910c` variant differs only in
   its ops package). Kept uniform — one package per backend key — at the cost of two redundant
   builds; revisit only if it causes real noise.
7. Cloning FlagCX from github.com on self-hosted runners may need a proxy. `FLAGCX_REPO` as an
   `ARG` is the escape hatch to the internal filestore, the route `packaging/vllm/` already
   takes.

## Sequencing

1. `backends.yaml` + `deb-config.py` + `--check` against `generate_matrix.py --runtime`.
2. `debian/` overlay (control.in, rules, changelog.sh, patch-soname.sh) with **metax first** —
   it already works today, so it isolates the new plumbing from SDK risk.
3. `Containerfile.deb` + `build-flagcx-deb.sh`, reproducing metax, then nvidia.
4. `verify/` + the `flagcx-deb.yml` workflow.
5. Fan out to the remaining ready backends, then one PR per probe-pending backend.
6. Documentation + registration.

## Verification

```bash
# matrix resolves and agrees with build-infra
python3 scripts/generate_matrix.py --runtime > /tmp/all.json
python3 packaging/flagcx/deb-config.py --merge /tmp/all.json   # one entry per enabled backend
python3 packaging/flagcx/deb-config.py --check                 # no drift

# metax first (known-good upstream), then nvidia
packaging/flagcx/build-flagcx-deb.sh --backend metax-maca3.8.1.3 \
    --ref "$FLAGCX_REF" --out debian-packages/metax-maca3.8.1.3
dpkg-deb -I debian-packages/metax-maca3.8.1.3/*.deb    # Depends / Provides / Conflicts / Architecture
dpkg-deb -c debian-packages/metax-maca3.8.1.3/*.deb    # SONAME symlink chain
packaging/flagcx/verify/verify-flagcx-deb.sh --backend metax-maca3.8.1.3 \
    --floor-image "ubuntu:${UBUNTU}" debian-packages/metax-maca3.8.1.3/*.deb
```

Then the two tests that prove the package is genuinely self-describing:

1. **In the matching base image** — install, then `ldd /usr/lib/.../libflagcx.so.0` must resolve
   cleanly and `smoke-load` must pass under `RTLD_NOW`.
2. **In a plain `ubuntu:24.04` / `ubuntu:22.04` container** (matching the package's
   `Depends: libc6` floor) — `apt-get install -y ./*.deb` must **exit 0**. This is the real test
   of the dependency set. Note deliberately: `ldd` in this container *will* report the vendor
   libraries as `not found`, and that is correct — they are supplied by the site runtime, not by
   Ubuntu. Only the non-vendor dependencies must resolve here.

Then a **negative test** on nvidia: drop `libnccl-dev` from `backends.yaml`'s `apt` list and
confirm the `assert` aborts the build instead of silently producing a collector-less `.so`.
Finally one Ascend backend on the `cann900` aarch64 runner, to exercise the arm64 stanza end to
end.

## Out of scope this round

- RPM (deferred; `packaging/rpm/` and its spec untouched).
- Any change to the FlagCX repository, including retiring its `build-deb.yml` /
  `upload-nexus.yml` — that is a small follow-up PR once this path is verified.
- Publishing to a repository. When it is wanted,
  `https://resource.flagos.net/repository/flagos-apt-hosted` already exists and build-infra's
  reusable `upload-nexus.yml` already targets it.
- On-node / hardware verification and a status matrix.
