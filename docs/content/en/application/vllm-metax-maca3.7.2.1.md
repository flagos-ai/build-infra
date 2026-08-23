---
title: "vllm-metax-maca3.7.2.1"
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

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-metax-maca3.7.2.1:2.1.2</code> <a href="../../runtime/metax-maca3.7.2.1/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### Application package

`vllm==0.24.0+flagos`

## Launch

**Not published yet — this image is not on the registry yet. The tag below is what the build pipeline will push once it is built for this backend.**

`harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2`

**With the container toolkit** *(optional)*:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 bash
```

Start the app with its default settings:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2
```

Pass arguments to the launcher:

```bash
metax-docker \
  run \
  --rm \
  -it \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 vllm-serve --model <path> --port 9000
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/mxcd \
  --device /dev/dri \
  --group-add video \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.7.2.1:2.1.2 vllm-serve --model <path> --port 9000
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
mx-smi
```
