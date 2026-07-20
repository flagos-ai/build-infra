---
title: "metax-maca3.7.2.1"
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

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** MetaX C550
- **Host driver:** 3.8.30
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: metax-docker >= 0.15.3

## Image contents

### Built on

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-base/flagos-base-metax-maca3.7.2.1:2.1.1</code> <a href="../base/metax-maca3.7.2.1/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### Major Python packages

- `flag_gems`
- `flagtree==3.1.0+metax3.7.2.0`
- `flash_attn==2.6.3+metax3.7.2.0torch2.8`
- `torch==2.8.0+metax3.7.2.0`
- `torchaudio==2.4.1+metax3.7.2.0`
- `torchvision==0.15.1+metax3.7.2.0`
- <span class="muted"><code class="plain">triton==3.0.0+metax3.7.2.0</code></span>

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Launch

**With the container toolkit** *(optional)*:

```bash
metax-docker \
  --gpus all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.7.2.1:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.7.2.1:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```
