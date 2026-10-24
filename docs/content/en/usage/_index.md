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

FlagTree is the default compiler in the runtime and app images, and it is
released frequently. Pick a version at container start instead of rebuilding:

```bash
docker run -e FLAGTREE_VERSION=0.7.0 <runtime-or-app-image> ...
```

The wheel is installed into `/opt/flagtree` before the application starts. In a
running container, `compiler flagtree <version>` does the same; `compiler` alone
prints the active version.

`latest` picks the newest **daily build** for that backend instead of a release:

```bash
docker run -e FLAGTREE_VERSION=latest <runtime-or-app-image> ...
```

Daily wheels lead the next release and are built every day, so this is the way to
run a fix that has not been released yet. It downloads about 120 MB and needs
egress at container start; the fetch happens once per container, so later shells
in the same container reuse it, and the next container picks up whatever was
published since.

**When the requested version cannot be installed, the container stops.** A
container running a FlagTree other than the one asked for is not what was asked
for, and nothing downstream would say so — so the request is refused, the reason
goes to stderr, and the exit is non-zero: `docker run` returns 1, and under
kubernetes the pod goes to `Error` (then `CrashLoopBackOff`) instead of coming up
Running on the wrong compiler, with `kubectl logs <pod>` — `--previous` for the
restart — carrying the reason. A backend the daily line does not build
(cambricon, spacemit, thead today) is refused the same way. Reaching an index
that does not answer is settled by a short probe (10s), so the failure arrives in
about ten seconds rather than after pip's own retries.

## Building on demand

Base images are built manually, not on every change (vendor SDKs change rarely):

- **CI:** run the **Base Image Build (manual)** GitHub Actions workflow
  (`workflow_dispatch`) — choose a backend (or `all`) and whether to push.
- **Locally:** `python base/build.py <vendor>-<backend> [--push]` (reads the
  registry from `.github/build-config.yml`).
