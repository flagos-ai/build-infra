# FlagCX deb packages

Builds `libflagcx-<backend>` / `libflagcx-<backend>-dev` `.deb` pairs out of a FlagCX git ref,
one backend per container. **`DESIGN.md` is the design of record** — why the packages look the
way they do, and what each `backends.yaml` field is for. This file is only how to run it.

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
builds one backend per runner and then verifies before uploading. Nothing publishes to the
Nexus apt repo yet; artifacts stop at the workflow.

Every build needs a Docker host that can reach the registry and pull the backend's base image.
The build itself takes the base image as-is and adds only `debhelper`/`fakeroot`/`devscripts`
plus the backend's `apt:` packages — no runtime image is involved.

## Adding a backend

1. Add an entry to `backends.yaml` under either the `ready` or `probe-pending` heading, with a
   `probe:` note saying what one in-container `make` + `ldd` still has to answer.
2. Run `python3 packaging/flagcx/deb-config.py --check` — it cross-checks the entry against the
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

## Verified

A row means both tests in `DESIGN.md` §Verification passed on the vendor's own node: the
`.deb` installs into its matching base image and its soname resolves with the vendor symbols
bound (`smoke-load` under `RTLD_NOW`), **and** `apt-get install` exits 0 in a plain Ubuntu at
the package's libc6 floor.

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
| `backends.yaml` | per-backend packaging facts: the one input build-infra cannot derive |
| `deb-config.py` | joins `backends.yaml` with `generate_matrix.py --runtime` |
| `Containerfile.deb` | the build, on top of the backend's base image |
| `debian/` | `rules` + `control.in`; `debian/control` is rendered on the host |
| `build-flagcx-deb.sh` | local/CI entry point, one backend per invocation |
| `verify/` | installs the built `.deb` into its base image and into a plain Ubuntu |

`debian/control` is **generated** — edit `control.in`, never the rendered file.
