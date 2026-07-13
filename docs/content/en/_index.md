---
title: build-infra
type: docs
---

# build-infra

FlagOS container image build infrastructure. This repo defines and builds the
**base images** — a vendor's SDK and toolchain on an OS base — that FlagOS
runtime images are built on.

- **[Overview]({{< relref "overview" >}})** — how images are layered and named.
- **[Images]({{< relref "images" >}})** — the supported vendor/backend catalog and a
  per-image reference (what's installed, the environment, dependencies).
- **[Usage]({{< relref "usage" >}})** — pulling and running the images.
- **[Contribution]({{< relref "contribution/onboarding" >}})** — adding a new vendor/backend.

Every fact on these pages is generated from `configs.yaml` + `base/`, so the docs
cannot drift from the source.
