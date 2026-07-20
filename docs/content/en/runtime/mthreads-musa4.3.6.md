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
---
title: "mthreads-musa4.3.6"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MThreads MTT S5000
- **Host driver:** 5.2.0-server
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: KUAE Cloud Native Toolkits (MT Container Toolkit) >= 2.1.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-mthreads-musa4.3.6:2.1.1`

### Python

3.10

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0+mthreads3.6`
- `mkl==2024.0.0`
- `torch==2.9.0+musa.4.3.6`
- `torch_musa==2.9.0`
- <span class="muted"><code class="plain">triton==3.6.0+git89458660</code></span>

<p class="muted"><em>Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).</em></p>

## Environment

- `MTHREADS_VISIBLE_DEVICES=all`
- `LD_LIBRARY_PATH=${VIRTUAL_ENV}/lib:${LD_LIBRARY_PATH}`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime mthreads \
  --env MTHREADS_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa4.3.6:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mtgpu.0 \
  --device /dev/dri \
  -v /usr/bin/mthreads-gmi:/usr/bin/mthreads-gmi:ro \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-mthreads-musa4.3.6:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mthreads-gmi
```
