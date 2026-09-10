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
