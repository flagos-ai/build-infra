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
title: "cambricon-neuware4.4.3"
---

## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Cambricon MLU590
- **Host driver:** 6.2.15

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-cambricon-neuware4.4.3:2.1.1-31-g853fdf7`

### Python

3.10

### Major Python packages

- `cambricon_dali==0.13.0`
- `flag_gems`
- `torch-mlu-ops==1.8.0+torch2.7.1`
- `torch-mlu==1.29.2+torch2.7.1`
- `torch==2.7.1+cpu`
- `triton==3.2.0+mlu1.7.2`

## Launch

Start an interactive shell (works with docker or podman):

```bash
docker run --rm -it \
  --device /dev/cambricon_dev0 \
  --device /dev/cambricon_ctl \
  flagos-runtime-cambricon-neuware4.4.3:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
cnmon
```
