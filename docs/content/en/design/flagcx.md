---
title: FlagCX
weight: 30
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


FlagCX is the collective-communication library (a NCCL-alike). build-infra
ships it on three channels, one backend per container, all reading one
`backends.yaml`:

- **`.deb`** — `libflagcx-<backend>` / `-dev` pairs into an apt repo named for
  the Ubuntu release its base image was built on (`flagos-apt-ubuntu24.04` /
  `-22.04`), so a user adds the repo matching their distro and never has to know
  a glibc floor exists.
- **wheels** — one wheel per backend on the vendor PyPI, installed by the exact
  pin (`flagcx==0.14.0+cuda12.8`). There is no `Provides:` in pip, so the exact
  pin is what stops two vendors' builds of one commit from colliding.
- **builder images** — self-contained `ubuntu:22.04` toolchain images for the
  rows whose wheel must link at most glibc 2.35 (so it installs on physical
  22.04 hosts), and for the rows whose runtime image carries no device toolchain
  at all.

## Why one artifact per backend

The library links the vendor's CCL and device headers, which differ per backend,
so a build is addressed by the `{vendor}-{backend}` key. The deb line ships one
package per backend for that reason; the wheel line does the same because pip
cannot express "the default variant answers to the unqualified name".

The chip (910B vs 910C, `sm_90` vs `sm_120`) is deliberately **not** a build
input: the device is chosen by the driver at run time, so one wheel serves both
chips of a backend.

## Version labels and pins

A wheel's local version label is the bare backend name (`+cuda12.8`,
`+maca3.7.2.1`, `+dtk2604`), with the `{vendor}-` prefix dropped — the wheel
already lands on a per-vendor index. The label leads the local segment so a
version range cannot cross into another backend's variants, and every install
uses `==` rather than `>=`.

## Where the glibc floor comes from

The deb line is addressed by distro (the base image's Ubuntu release). The wheel
line needs a floor the runtime image cannot always provide: a 24.04 runtime
links GLIBC 2.38, which aborts on the physical 22.04 hosts the offline bundle
installs to. The builder channel solves that by being self-contained on
`ubuntu:22.04` — its own interpreter, torch pin and SDK — so the floor drops to
2.35 without touching the runtime or FlagTree. The floor is asserted at the
artifact (`objdump`-based), not remembered as an image digest.

## Full rationale

The design of record lives beside the code:

- [packaging/flagcx/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagcx/DESIGN.md) — the deb line's decisions.
- [packaging/flagcx/WHEEL-DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagcx/WHEEL-DESIGN.md) — the wheel and builder lines' decisions.
- [packaging/flagcx/backends.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagcx/backends.yaml) — the per-backend packaging facts.
