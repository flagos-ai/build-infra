---
title: "enflame-tops1.10.6"
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
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.10.6
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: tencent-container-toolkit >= 2.0.52

## Image contents

### Built on

<div class="ms-3"><code class="plain">harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.10.6:2.1.2</code> <a href="../../base/enflame-tops1.10.6/" title="View base image details" aria-label="View base image details"><i class="material-icons align-middle size-20">open_in_new</i></a></div>

### Python

3.12

### Major Python packages

- `enflame-modelopt==3.6.20260615+torch.2.11.0`
- `flag_gems==5.3.4`
- `flagtree==0.6.1+enflame3.6`
- `flash-attn==2.7.2+torch.2.11.0.gcu.3.8.20260706`
- `numpy==2.3.5`
- `pyefml==1.10.6`
- `tops-extension==3.6.20260529+torch.2.11.0`
- `topstx==1.10.6`
- `torch-gcu==2.11.0+3.8.20260713`
- `torch==2.11.0+cpu`
- `torchaudio==2.11.0+cpu`
- `torchcodec==3.8.20260624+torch.2.11.0`
- `torchvision==0.26.0+cpu`
- <span class="muted"><code class="plain">triton==3.6.0 (+ triton-gcu==3.6.0+1.0.20260722)</code></span>

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Environment

- `TORCH_GCU_ENABLE_INT64_AND_UINT64=1`
- `ENABLE_I64_CHECK=0`
- `TORCHGCU_INDUCTOR_ENABLE=1`
- `ENFLAME_PT_OP_DEBUG_CONFIG=fallback_cpu=all_ops`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.10.6:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.10.6:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```
