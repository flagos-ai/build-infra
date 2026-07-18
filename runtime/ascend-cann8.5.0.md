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

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-ascend-cann8.5.0:2.1.1-31-g853fdf7`

### Python

3.11

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0+ascend3.2`
- `torch-npu==2.9.0`
- `torch==2.9.0+cpu`
- `triton-ascend==3.2.0` *(fallback)*

*Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).*

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  -e ASCEND_VISIBLE_DEVICES=0 \
  flagos-runtime-ascend-cann8.5.0:latest bash
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
  flagos-runtime-ascend-cann8.5.0:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh && npu-smi info
```
