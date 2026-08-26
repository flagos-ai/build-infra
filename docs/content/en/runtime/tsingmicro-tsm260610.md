---
title: "tsingmicro-tsm260610"
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
- **Chip models:** Tsingmicro TX8110
- **Host driver:** 260610164501.01
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: tx-container-toolkit >= 2.5.0

## Image contents

### Built on

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-base/flagos-base-tsingmicro-tsm260610:2.1.2</code> <a href="../../base/tsingmicro-tsm260610/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.10

### Major Python packages

- `flag_gems==5.3.5`
- `flagtree==0.6.1+tsingmicro3.3`
- `numpy==2.2.6`
- `torch==2.11.0+cpu`
- `torch_txda==0.1.0+20260728.f6fbdb71`
- `torchaudio==2.11.0+cpu`
- `torchvision==0.26.0+cpu`
- <span class="muted"><code class="plain">triton==3.6.0.post2026072919+git8f5b0609</code></span>
- `txops==0.1.0+20260716.e94d9509`

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Environment

- `USE_TORCH_XLA=0`
- `TORCH_COMPILE_DISABLE=1`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --runtime=tsingmicro \
  -e TSINGMICRO_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm260610:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/accel \
  --device /dev/accel_drv_mgr \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-tsingmicro-tsm260610:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
tsm_smi
```
