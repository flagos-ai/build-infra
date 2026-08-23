---
title: "vllm-cambricon-neuware4.7.2"
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
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.5.48

## Image contents

### Built on

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.2:2.1.2</code> <a href="../../runtime/cambricon-neuware4.7.2/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### Application package

`vllm==0.24.0+flagos`

## Launch

**Not published yet — this image is not on the registry yet. The tag below is what the build pipeline will push once it is built for this backend.**

`harbor.baai.ac.cn/flagos-app/vllm0.24.0-cambricon-neuware4.7.2:2.1.2`

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-cambricon-neuware4.7.2:2.1.2 bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-cambricon-neuware4.7.2:2.1.2
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-app/vllm0.24.0-cambricon-neuware4.7.2:2.1.2 vllm-serve --model <path> --port 9000
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```
