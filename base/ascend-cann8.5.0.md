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
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Base image

`ubuntu:24.04`

### System packages

Explicitly installed; the version is the one baked into this image:

- `ca-certificates` — 20260601~24.04.1
- `software-properties-common` — 0.99.49.4

### SDK components

- CANN Toolkit 8.5.0 (aarch64)
- CANN 910B Ops 8.5.0 (aarch64)

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1 bash
```

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
  harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh && npu-smi info
```
