# FlagTree wheels — design

Status: **implemented.** `README.md` is the operator/author-facing companion (how to run each
builder, what each `backends.yaml` field is for, the full per-backend walkthrough); this file
is the design of record — why, not what. `backends.yaml` is the live list of which backends
have a Containerfile and whether the daily line builds them.

Goal: build FlagTree (the Triton fork) wheels for a backend from source, so the wheel is
self-owned and reproducible — and an A/B baseline against the vendor's own wheel.

## Context

The vendor wheels have real defects that only a source build can close: MetaX's was built on
Ubuntu 24.04 and linked `libtriton.so` against `GLIBC_2.38` / `GLIBCXX_3.4.32` (aborts on
22.04 nodes before `main()`); its current one still ships debug info (793.7 MB `libtriton.so`)
and no `Source-Commit` provenance. A plain 22.04 rebuild yields size + provenance, and both
are worth gating on.

### Decisions taken

| Question | Decision |
|---|---|
| Why source-build | Self-owned, reproducible, A/B baseline against the vendor wheel; closes the glibc/ABI and provenance gaps the vendor wheels carry |
| Build base | Bare `ubuntu:22.04` (glibc 2.35) for 9 backends, so the resulting `libtriton.so` loads on 22.04 nodes; the ascend pair starts from **its backend's runtime image** because the Ascend build needs CANN on the build machine |
| One Containerfile per backend | Yes — 11 files beside `backends.yaml`, not one parameterised file; each backend's toolchain staging differs enough that a single file would grow a per-vendor `if` ladder (the metax pybind11/plugin pin is nothing like the ascend CANN line) |
| `--target builder` split | The builder stage is everything that does not depend on the FlagTree ref (apt toolchain, interpreter, prebuilt LLVM / plugin / triton toolkits staged into FlagTree's offline cache); the default target clones the ref and compiles on top. The stage is published, so a warm build pays for clone + compile only |
| pybind11 | **Pinned** (`pybind11==3.0.1`), not just declared `>=`: it is an ABI contract — the prebuilt `metaxTritonPlugin.so` is compiled against pybind11 internals **v11**, and an unpinned build pulls 3.1.0 (internals **v12**) that imports fine but fails at kernel-compile time. The gate compares rather than asserting a literal, so pin and gate cannot drift |
| glibc floor enforcement | A post-build **objdump gate** fails the build if any 22.04-incompatible symbol (`GLIBC_2.38`, `GLIBCXX_3.4.31/32`, `__isoc23_*`) reappears in `libtriton.so` |
| Provenance | `Project-URL: Source-Commit, …` in the wheel METADATA, written via a `setup.cfg` carrier the build drops into the clone — zero FlagTree source changes. One lookup answers both "which FlagTree" and "which commit" |
| Build-line facts | `backends.yaml`, not a second `configs.yaml`: the image tag, stack version and vendor index stay in `configs.yaml` / `build-config.yml` and are derived at run time |
| Adding a backend | One `backends.yaml` entry, not a new workflow or second job: the builder matrix and the daily line both read the same file |
| Stage proof | Either a named `verify_stage` (a workflow step, for a contract a path list cannot express) or a `verify` block (the same assertions as data, rendered by one generic step). A backend staged like its predecessors needs a row and no new step |
| Stage tag | Flat, tagged with the stack version (`configs.yaml` `version:`); a rebuild overwrites it |
| Daily version | `<version_base>.dev<UTC date>` in the **public** segment — the only placement that is both a pre-release (a plain `pip install flagtree` still resolves to the release) and numerically above the release it leads. A dated *release* segment would shadow the release |
| Daily distribution | One per backend (`flagtree-nvidia`, …): the backend is the distribution name, not a version token. A backend token in the local segment cannot be matched by a `==` specifier anyway (`dev` inside a local label compares as text) |
| Daily commit | In the metadata (`Source-Commit`), never the filename. FlagTree appends `+git<sha8>` to any version it is handed, so a date-only version requires dropping `.git` before `pip wheel` and carrying the sha through `setup.cfg` |
| Missed daily | Permanent gap: the plan computes `<version_base>.dev<today UTC date>` and takes no date input, so a later dispatch publishes the later date (#1411's 2026-10-18 gap is the record) |
| Empty-matrix failure | The matrix is assigned to a variable before writing to `$GITHUB_OUTPUT`, so a failed plan carries jq's exit status into `set -e` instead of silently skipping the build job green |

## Not here

- The FlagTree source itself — the wheel build clones `flagos-ai/flagtree` and overlays only a
  `setup.cfg` carrier + a `patch-flagtree-version.py` metadata rewrite; upstream is not forked.

## See also

- `packaging/flagtree/README.md` — how to run each builder, the full per-backend walkthrough.
- `packaging/flagtree/backends.yaml` — the build-line facts (containerfile, builder image,
  runner, disk budget, `verify`, `daily:`).
- Docs site: Design → FlagTree (operator summary, links back here).
