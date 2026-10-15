---
title: Packaging Channels
weight: 55
---

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

How FlagOS artifacts are distributed: which channel carries what, how
repositories are laid out, and how packages are named and versioned. The
layout was agreed in
[build-infra#600](https://github.com/flagos-ai/build-infra/issues/600); this
page is the reference for wiring the upload workflows and for onboarding new
components.

## Two channels

| Channel | Carries | Installed with |
|---|---|---|
| **deb/rpm repos** (per target distro) | Native libraries (`flagcx`, `libtriton-jit`, `flagtree`, ...) and pure-Python FlagOS packages (`flag_gems`, `flag_attn`, ...) | `apt install` / `dnf install` |
| **PyPI indexes** (per vendor: `flagos-pypi-<vendor>`) | Everything tied to a vendor toolchain: vendor-customized torch (`torch==X.Y.Z+musa`), vendor operator packages (`torch_musa`, `torch_npu`, ...), binary operator extras (`flag_gems_cpp_<vendor>`) | `pip install --index-url .../flagos-pypi-<vendor>/simple ...` |

**The boundary rule: a package goes to deb/rpm if and only if the distro
channel can actually carry it.**

Pure-Python (arch:all / noarch) packages qualify. One build serves every
suite, their dependencies are stable, and shipping them natively is what
makes the *stack* deliverable through distro repositories: official inclusion
in openEuler / openKylin / deepin requires the whole dependency closure as
native packages, and air-gapped or compliance-managed hosts install and patch
only through the distro package manager, so one `dnf install` must resolve
the full stack, Python layer included.

Vendor-toolchain binaries do not qualify:

- the (python x torch x SDK x distro) version matrix cannot be expressed in
  deb/rpm naming, while pip environment markers and an index per vendor
  handle it naturally;
- several vendor SDKs are not redistributable, so a public deb/rpm could
  neither carry nor depend on the runtime it needs;
- the wheels are GB-sized and fast-moving;
- two artifacts sharing one name and version (`torch==2.9.1+musa` vs
  upstream `torch==2.9.1`) cannot coexist in one apt/yum suite at all — on
  the pip side the per-vendor index URL is the discriminator, so no tool has
  to tell same-named wheels apart by metadata.

deb/rpm never replaces the PyPI channel; the two coexist. The deb/rpm side
must stay installable on its own: **no hard dependency may point at the pip
layer.** The bridge is soft — installation docs point to the vendor pip
index, or a meta-package's `Recommends`/description does.

## Source packages

Besides wheels, every package in the catalog also has a source tarball download —
a `.tar.gz` URL you can fetch directly. There is no separate source repository:
**these URLs point at the release tags of the upstream GitHub repositories**
(`https://github.com/<repo>/archive/refs/tags/<tag>.tar.gz`).

Each package's source information is recorded in the `sources:` block of
`packaging/packages.yaml` — a top-level key alongside `wheels:`, matching it
one package per entry. An entry carries:

| Field | Meaning |
|---|---|
| `short_name`, `desc_zh`, `desc_en` | the source entry's title and description on the site |
| `url` | download-URL template, with `{version}` as its only placeholder |
| `versions[].version` | the source's own version |
| `notes`, `notes_en` | how this source differs from the package's wheels (written only when it does; `notes` in Chinese, `notes_en` in English) |

**Source versions are independent of wheel versions**; only the package names
correspond. One source can produce a batch of platform build variants
(`flagcx`'s 20 platform wheels come from one source version, `0.14.0`;
`torch-fl`'s 7 come from one, `2.10.0`), and one wheel version can have its own
source (`flagtree`'s 14 backends each have one). `megatron-core`'s source
version is the fork branch number `0.2.3`, unrelated to the wheel's `0.17.1`.
A source version therefore cannot be derived from a wheel version; it is
recorded per entry — 14 packages, 55 wheel versions, 30 source versions in all.

Fill a version from `versions[]` into `{version}` to get the download URL.
`vllm`'s template, for instance, is
`https://github.com/vllm-project/vllm/archive/refs/tags/v{version}.tar.gz`,
so version `0.24.0` gives
`https://github.com/vllm-project/vllm/archive/refs/tags/v0.24.0.tar.gz`.

Most packages' templates read `.../tags/v{version}.tar.gz` — the tag differs
from the version only by a leading `v`; `flagtree`'s upstream tags have no `v`
prefix. Percent-encode the tag segment before requesting the URL (write `+` as
`%2B`) — `flagtree`'s versions carry a `+`.

Unlike `wheels:`, `sources:` is maintained by hand in full: a repository does
not change with a publish, and no publish step can observe it. (The publish
facts under `wheels:` are recorded automatically by the publish steps — see
`docs/wheel-info.md`.)

The source tarballs the build actually consumes (`vllm-<version>.tar.gz`,
`sglang-<version>.tar.gz`) are kept separately on the internal filestore
(`https://resource.flagos.net/repository/flagos-filestore/<project>/`) so that
the same source can be built again.

## Repository layout

- **apt**: one hosted repository per target distro release
  (`flagos-apt-<distro><ver>`). An apt-hosted Nexus repository carries
  exactly one distribution, and apt has no group repositories.
- **yum**: one hosted repository with per-subpath repodata:
  `flagos-yum-hosted/<distro>/<ver>/<arch>/`, e.g. `openeuler/24.03/x86_64`,
  `fedora/43/x86_64`.
- **arch:all / noarch packages are copied into every suite they apply to** —
  there is no separate "shared" repository. Users need one sources line, and
  per-suite dependency floors (e.g. a different sqlalchemy minimum) stay
  expressible.

## Versioning

- deb: a distro suffix on the Debian revision, `+<distro><ver>`
  (`0.6.0-1+ubuntu22.04`) — it sorts above the plain revision and upgrades
  unsuffixed packages cleanly.
- rpm: `%{?dist}` (`.oe2403`, `.fc43`, `.el9`) — auto-expanded when building
  inside the target distro's container, or passed explicitly otherwise.
- Package versions follow upstream tags; build scripts must read the version
  from packaging metadata, never hardcode it.

## Naming

- Native libraries, one package per platform: `libflagcx-<platform>`,
  `libtriton-jit-<vendor>`, `python3-flagtree-<backend>`. Platform and
  backend names follow the upstream identifiers.
- Same-platform packages of one component are mutually exclusive across
  backends: `Conflicts` in deb; file conflicts on the shared soname in rpm.
- Pure-Python packages: `python3-<upstream-name>`, unmodified upstream
  source.

## Vendor-library dependencies

Choose per (distro x component), in this order:

1. **Native** — the distro, or the vendor's official repository for that
   distro, provides the library as an RPM/deb: declare normal dependencies.
   Example: CUDA on Fedora 43 via NVIDIA's fedora repository.
2. **Partially native** — only some libraries have providers: exclude just
   the missing ones. Example: `external_ccl_runtime` excluding only
   `libnccl.so.2` on Fedora 43 (NCCL has no Fedora RPM).
3. **No providers** — exclude the vendor libraries entirely
   (`external_vendor_runtime`, as on openEuler); the deployment environment
   supplies ABI-compatible libraries, typically via the vendor pip index.

Explicit versioned requires (`Requires: libnccl >= 2.27`) accompany the
auto-generated soname requires wherever a version floor matters.

## Out of scope / future

- Model-layer repositories (FlagScale, slang, megatron, verl, ...) are not
  packaged as deb/rpm for now.
- A self-extracting offline bundle (toolkit-style: local repository +
  install script) can later be generated from the same per-suite repos for
  air-gapped delivery. It layers on top of this design and does not change
  it.
