---
title: FlagTree
weight: 20
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


FlagTree (the Triton fork) is the default compiler in runtime and app images.
It is built from source into per-backend wheels, rather than installed from a
vendor's wheel.

## Why source-built

The vendor wheels carry defects a source build closes:

- **Old glibc links** — MetaX's was built on Ubuntu 24.04 and linked
  `libtriton.so` against `GLIBC_2.38`/`GLIBCXX_3.4.32`, which abort on 22.04
  nodes before `main()`.
- **Debug bloat** — the current MetaX wheel ships 793.7 MB of `libtriton.so`
  debug sections against ~218 MB for the release build here.
- **No provenance** — vendor wheels carry no `Source-Commit`.

A source build also gives an A/B baseline against the vendor's wheel.

## Build shape

Each backend has its own Containerfile beside `packaging/flagtree/backends.yaml`
(11 backends). The build splits into two stages:

- **`--target builder`** — everything that does not depend on the FlagTree ref:
  the apt toolchain, the interpreter, and the prebuilt LLVM/plugin/triton
  toolkits staged into FlagTree's offline cache. This stage is published, so a
  warm build only pays for the clone and the compile.
- **default target** — clones the ref and compiles on top of the published stage.

Nine backends start from a bare `ubuntu:22.04` (old glibc, so `libtriton.so`
loads on 22.04 nodes); the ascend pair starts from its own runtime image because
the Ascend build needs CANN on the build machine.

Two hard gates back the "reproducible" claim: an objdump gate fails the build on
any 22.04-incompatible symbol, and the smoke test requires the `Source-Commit`
metadata carrier.

## Daily line

A daily workflow publishes one wheel per day per backend, as a **separate
distribution** per backend (`flagtree-nvidia`, `flagtree-metax`, …). The version
is `<version_base>.dev<UTC date>`, placed in the public segment so a plain
`pip install flagtree` keeps resolving to the release while "newest daily" is a
plain version comparison.

The commit a daily was built from is in its metadata
(`Project-URL: Source-Commit`), never the filename.

## Full rationale

- [packaging/flagtree/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagtree/DESIGN.md) — the decisions, maintainer-facing.
- [packaging/flagtree/README.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagtree/README.md) — how to run each builder, per-backend.
- [packaging/flagtree/backends.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/flagtree/backends.yaml) — the build-line facts.
