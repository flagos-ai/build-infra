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

# build-infra

FlagOS container image build infrastructure. This repo defines and builds the
**base images** — a vendor's SDK and toolchain on an OS base — that FlagOS
runtime images are built on.

📖 **Documentation: https://flagos-ai.github.io/release-info/**

The docs (supported backends, per-image environment, dependencies) are generated
from `configs.yaml` + `base/`, so they can't drift from the source.

## Layout

| Path                        | What                                                        |
|-----------------------------|-------------------------------------------------------------|
| `configs.yaml`              | Source of truth: per-backend deps, versions, image env      |
| `base/<vendor>-<backend>`   | Base image containerfiles                                   |
| `scripts/build_base.py`     | Build a base image (reads OCI labels + registry)            |
| `scripts/generate_matrix.py`| Emit the CI build matrix from `configs.yaml`                |
| `scripts/build_runtime.py`  | Build a runtime image                                       |
| `.github/build-config.yml`  | Global build config: registry + per-backend runners         |
| `runtime/`                  | Runtime Containerfile + per-image readmes                   |
| `flagtree-builder/`         | Low-glibc FlagTree wheel builders                           |
| `docs/`                     | Hugo docs site + data-generation scripts                    |

## Quick start

Build a base image locally:

```bash
python scripts/build_base.py nvidia-cuda12.8 --dry-run   # preview
python scripts/build_base.py nvidia-cuda12.8 --push      # build + push
```

In CI, base images are built on demand via the **Base Image Build (manual)**
workflow (`workflow_dispatch`) — pick a backend (or `all`) and whether to push.

To add a vendor/backend, see the
[onboarding guide](https://flagos-ai.github.io/release-info/contribution/onboarding/).
