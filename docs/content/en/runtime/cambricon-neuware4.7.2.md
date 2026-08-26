---
title: "cambricon-neuware4.7.2"
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

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.7.2:2.1.2</code> <a href="../../base/cambricon-neuware4.7.2/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### Major Python packages

- `flag_gems==5.3.5`
- `numpy==2.2.6`
- `pandas==3.0.5`
- `torch-mlu-ops==1.12.1+torch2.11.0`
- `torch-mlu==1.33.1+torch2.11.0`
- `torch==2.11.0+cpu`
- `triton==3.4.0+mlu2.1.1`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-cambricon-neuware4.7.2:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```
