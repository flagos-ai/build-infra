---
title: "megatron-rl-ascend-cann8.5.0"
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

- **Architecture:** aarch64
- **Chip models:** Ascend 910B
- **Host driver:** 25.5.0
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann8.5.0:2.1.2</code> <a href="../../runtime/ascend-cann8.5.0/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.11

### Application package

`megatron-core[rl]==0.17.1`

## Launch

**Not published yet — this image is not on the registry yet. The tag below is what the build pipeline will push once it is built for this backend.**

`harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-ascend-cann8.5.0:2.1.2-0.2.1`

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-ascend-cann8.5.0:2.1.2-0.2.1 bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.


**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-ascend-cann8.5.0:2.1.2-0.2.1 bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.


## Verify

Inside the container, confirm the accelerator is visible:

```bash
npu-smi info
```
