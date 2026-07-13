---
title: build-infra
type: docs
---

# build-infra

FlagOS container image build infrastructure. FlagOS ships images in layers — a
vendor **base** image, a FlagGems **runtime** image on top of it, and (soon)
**application** images.

- **[Overview]({{< relref "overview" >}})** — how the image layers relate and are named.
- **[Base images]({{< relref "base" >}})** — OS + vendor SDK. Contents and run command per backend.
- **[Runtime images]({{< relref "runtime" >}})** — Python + software stack (torch, triton, flagtree, FlagGems).
- **[Application images]({{< relref "application" >}})** — vLLM, Megatron-LM, SGLang (roadmap).
- **[Usage]({{< relref "usage" >}})** · **[Contribution]({{< relref "contribution/onboarding" >}})**

Every fact on these pages is generated from `configs.yaml` + `base/`, so the docs
cannot drift from the source.
