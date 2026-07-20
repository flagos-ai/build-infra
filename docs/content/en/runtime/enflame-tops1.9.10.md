---
title: "enflame-tops1.9.10"
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
- **Host driver:** 1.9.10
- **Container toolkit** <em>(optional)</em> <button type="button" class="toolkit-optional-info" data-bs-toggle="tooltip" data-bs-title="only for the toolkit launch below; the plain docker/podman command needs none" aria-label="only for the toolkit launch below; the plain docker/podman command needs none">&#9432;</button>: tencent-container-toolkit >= 2.0.52

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.1`

### Python

3.12

### Major Python packages

- `flag_gems`
- `flagtree==0.6.0+enflame3.6`
- `flash-attn==2.7.2+torch.2.9.1.gcu.3.4.20260323`
- `pyefml==1.9.10`
- `torch-gcu==2.10.0+3.7.20260408`
- `torch==2.10.0+cpu`
- `torchaudio==2.10.0+cpu`
- `torchvision==0.25.0+cpu`
- <span class="muted"><code class="plain">triton-gcu==3.6.0+1.0.20260521.cc.1.9.10</code></span>

<p class="muted"><em>Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).</em></p>

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.9.10:latest bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --device /dev/gcu \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.9.10:latest bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```
