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
| `base/build.py`             | Build a base image (reads OCI labels + registry)            |
| `base/generate_matrix.py`   | Emit the CI build matrix from `configs.yaml`                |
| `.github/build-config.yml`  | Global build config: registry + per-backend runners         |
| `runtime/`                  | FlagGems runtime image build system                         |
| `flagtree-builder/`         | Low-glibc FlagTree wheel builders                           |
| `docs/`                     | Hugo docs site (data-driven from the files above)           |

## Quick start

Build a base image locally:

```bash
python base/build.py nvidia-cuda12.8 --dry-run   # preview
python base/build.py nvidia-cuda12.8 --push      # build + push
```

In CI, base images are built on demand via the **Base Image Build (manual)**
workflow (`workflow_dispatch`) — pick a backend (or `all`) and whether to push.

To add a vendor/backend, see the
[onboarding guide](https://flagos-ai.github.io/release-info/contribution/onboarding/).
