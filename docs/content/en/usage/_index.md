---
title: "Using the images"
weight: 50
---

## Pull

Image names and tags are on each backend's page under
[Base images]({{< relref "/base" >}}) and [Runtime images]({{< relref "/runtime" >}}).
For example:

```bash
docker pull harbor.baai.ac.cn/flagbase/flagos-base-nvidia-cuda12.8:2.1.0-0
```

## What's preset

Each base image bakes the vendor SDK environment (`PATH`, `LD_LIBRARY_PATH`, and
vendor-specific variables) directly as `ENV` — you don't need to source any
script. The exact variables, and a ready-to-copy `docker run` command, are on each
image's page.

## Building on demand

Base images are built manually, not on every change (vendor SDKs change rarely):

- **CI:** run the **Base Image Build (manual)** GitHub Actions workflow
  (`workflow_dispatch`) — choose a backend (or `all`) and whether to push.
- **Locally:** `python base/build.py <vendor>-<backend> [--push]` (reads the
  registry from `.github/build-config.yml`).
