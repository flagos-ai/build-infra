# packaging/flash-attn — flash-attn source-built wheels (nvidia)

Builds a source-compiled `flash_attn` wheel, ABI-locked to a specific
nvidia runtime image's torch. This is the **only self-built nvidia
deps_app package**: Megatron's RL dynamic-batching engine
hard-depends on flash-attn ≥ 2.7.3, and no usable binary wheel exists
for torch 2.10/2.11.

## Why self-built

- GitHub's newest cu12 wheel is `2.8.3.post1+cu12torch2.8` — built
  against torch 2.8's libtorch. On torch 2.10.0+cu128 it dies at
  import with
  `undefined symbol: c10_cuda_check_implementation` (ABI mismatch).
- FA3 / FA4 have no wheels at all (`flash_attn_3` absent from both
  GitHub releases and the aliyun mirror).
- TE is NOT needed — `--transformer-impl local` runs the full chain
  without it (metax precedent), so flash-attn is the only package to
  build.

## ABI contract

The compiled `.so`'s runtime ABI is bound to the **build-time torch**.
The Containerfile pip-installs `TORCH_VERSION` from `TORCH_INDEX` —
that version must equal the target runtime image's torch exactly.
One wheel per backend, distinguished by the PEP 440 local segment:

| Backend | Runtime torch | WHEEL_TAG | Wheel |
|---|---|---|---|
| nvidia-cuda12.8 | `2.10.0+cu128` | `fl.cu128.torch210` | `flash_attn-2.8.3.post1+fl.cu128.torch210-cp312-cp312-linux_x86_64.whl` |
| nvidia-cuda13.3 | `2.11.0+cu130` | `fl.cu130.torch211` | `flash_attn-2.8.3.post1+fl.cu130.torch211-cp312-cp312-linux_x86_64.whl` |

## Build

Build environment = the nvcr devel image (`nvcc` + cuDNN baked in).
No GPU needed — pure compilation. The two nvidia backends reuse the
same Containerfile; only three ARGs differ. Torch installs from the
**vendor PyPI** (`flagos-pypi-nvidia` — the same index the runtime
image installs torch from, so the build-time torch is byte-identical
to the runtime torch); `TORCH_INDEX` is overridable but defaults to it.

```bash
docker build -t flash-attn-wheel:build \
  --build-arg BASE_IMAGE=nvcr.io/nvidia/cuda:12.8.0-devel-ubuntu24.04 \
  --build-arg TORCH_VERSION=2.10.0+cu128 \
  --build-arg WHEEL_TAG=fl.cu128.torch210 \
  packaging/flash-attn/

cid=$(docker create flash-attn-wheel:build)
docker cp "$cid:/wheels/." /tmp/fa-wheels/ && docker rm "$cid"
```

The build image runs its own gates (gate + smoke steps): wheel shape
(`flash_attn_2_cuda*.so` present), METADATA version
(`2.8.3.post1+<WHEEL_TAG>`), and an import of the installed wheel
proving the `.so` links against the pip'd torch. Kernel execution is
verified on-node by the megatron RL E2E.

## Upstream build-system facts (non-obvious, verified against
v2.8.3.post1 setup.py)

- `FLASH_ATTENTION_FORCE_BUILD=TRUE` is **required** — otherwise the
  custom `bdist_wheel` (`CachedWheelsCommand`) tries to
  `urlretrieve` a prebuilt wheel from GitHub releases (the
  wrong-ABI `cu12torch2.8` artifact; hangs on the firewalled
  network).
- Arch control is `FLASH_ATTN_CUDA_ARCHS` (default `80;90;100;120`),
  **not** `TORCH_CUDA_ARCH_LIST` (ignored). H20 → `90` (sm_90).
- Version injection is the `FLASH_ATTN_LOCAL_VERSION` env, read by
  `get_package_version()` → `{public}+{local}`. No sed patch.
- Source = aliyun sdist (`pip download --no-binary :all: --no-build-isolation`),
  **not** a git clone: the clone path runs `git submodule update --init`
  for `csrc/cutlass` + `csrc/composable_kernel` against GitHub, while
  the sdist carries both vendored. `--no-build-isolation` matters
  because flash-attn has no `pyproject.toml` (isolation would run
  setup.py without torch). Metadata prep imports torch, so the
  download RUN must come after the torch install.
- The CUDA build produces exactly one extension, `flash_attn_2_cuda`
  (imported at runtime as `flash_attn_gpu`). The second
  `ext_modules.append` in setup.py is the ROCm branch (`IS_ROCM`
  only) and never fires on CUDA.
- Downgrade ladder if a compile fails: 2.8.3.post1 → 2.8.3 → 2.8.2 →
  2.7.4.post1 (all satisfy the megatron ≥ 2.7.3 gate).

## Consumption chain (already wired — no code changes)

`configs.yaml deps_app.megatron_rl` → `scripts/generate_matrix.py`
(`matrix.app_deps`) → `megatron-app-image.yml` `--build-arg
APP_DEPS` → `app/megatron/Containerfile.rl` vendor-PyPI install.

The upload step lives in `.github/workflows/flash-attn-wheel.yml`
(twine → `flagos-pypi-nvidia`); `configs.yaml` pins the exact wheel
with `==`, so the build, the PyPI upload, and the app-image install
all agree on one artifact.
