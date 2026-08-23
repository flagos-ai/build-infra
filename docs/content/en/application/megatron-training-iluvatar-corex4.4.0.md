---
title: "megatron-training-iluvatar-corex4.4.0"
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
- **Chip models:** Iluvatar BI-V150
- **Host driver:** 4.4.0
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: ix-container-toolkit >= 1.1.0

## Image contents

### Built on

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-iluvatar-corex4.4.0:2.1.2</code> <a href="../../runtime/iluvatar-corex4.4.0/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### Application package

`megatron-core[training]==0.17.1`

## Launch

**Not published yet — this image is not on the registry yet. The tag below is what the build pipeline will push once it is built for this backend.**

`harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.4.0:2.1.2-0.2.1`

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.4.0:2.1.2-0.2.1 bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.4.0:2.1.2-0.2.1
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --runtime iluvatar \
  --env IX_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.4.0:2.1.2-0.2.1 megatron-train --model-type GPT
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.4.0:2.1.2-0.2.1 bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.4.0:2.1.2-0.2.1
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/iluvatar0 \
  -v /usr/local/corex:/usr/local/corex:ro \
  harbor.baai.ac.cn/flagos-app/megatron_training0.17.1-iluvatar-corex4.4.0:2.1.2-0.2.1 megatron-train --model-type GPT
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
ixsmi
```
