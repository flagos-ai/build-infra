---
title: Usage
weight: 30
---

# Using the images

## Pull

Image names and tags are in the [catalog]({{< relref "images" >}}). For example:

```bash
docker pull harbor.baai.ac.cn/flagbase/flagos-base-nvidia-cuda12.8:2.1.0-0
```

## What's preset

Each base image bakes the vendor SDK environment (`PATH`, `LD_LIBRARY_PATH`, and
vendor-specific variables) directly as `ENV` — you don't need to source any
script. The exact variables per image are in the
[per-image reference]({{< relref "images/reference" >}}).

## Building on demand

Base images are built manually, not on every change (vendor SDKs change rarely):

- **CI:** run the **Base Image Build (manual)** GitHub Actions workflow
  (`workflow_dispatch`) — choose a backend (or `all`) and whether to push.
- **Locally:** `python base/build.py <vendor>-<backend> [--push]` (reads the
  registry from `.github/build-config.yml`).
