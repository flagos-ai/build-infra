---
title: "Using the images"
weight: 50
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

## Choosing a FlagTree version

Runtime and app images ship FlagTree as the default compiler (`/flagos` is the
Python environment, FlagTree lives in `/opt/flagtree`). FlagTree is released
frequently, and rebuilding the runtime would mean rebuilding every app image on
top of it — so the version can instead be chosen when the container starts:

```bash
docker run -e FLAGTREE_VERSION=0.7.0 <runtime-or-app-image> ...
```

The requested wheel is installed into `/opt/flagtree` before the application
starts; later shells in the same container reuse it. `-e FLAGTREE_VERSION=0.7.0`
installs what this backend publishes for that release — often a lane build such
as `0.7.0+<backend>3.6`. Write the full `+`-suffixed version to ask for a
particular build, including another backend's. In a container that is already
running, `compiler flagtree <version>` does the same. `compiler` alone prints the
active version, and `compiler triton` switches to the vendor Triton.

## Building on demand

Base images are built manually, not on every change (vendor SDKs change rarely):

- **CI:** run the **Base Image Build (manual)** GitHub Actions workflow
  (`workflow_dispatch`) — choose a backend (or `all`) and whether to push.
- **Locally:** `python base/build.py <vendor>-<backend> [--push]` (reads the
  registry from `.github/build-config.yml`).
