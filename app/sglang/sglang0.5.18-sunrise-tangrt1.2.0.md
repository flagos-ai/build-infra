## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Sunrise SR-SUN-S2-X1
- **Host driver:** 0.24.0

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-sunrise-tangrt1.2.0:2.2.0`

### Python

3.10

### Application package

`sglang==0.5.18+flagos`


`sglang-fl==0.1.dev1+g3b94dae1f`

## Environment

- `TORCHINDUCTOR_COMPILE_THREADS=1`
- `SGLANG_IS_FLASHINFER_AVAILABLE=false`
- `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1`
- `SGLANG_FL_FLAGOS_BLACKLIST=_scaled_dot_product_attention_math,pow_scalar,pow_tensor_scalar,pow_tensor_tensor`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/sglang0.5.18-sunrise-tangrt1.2.0:2.2.0-0.1.dev1_g3b94dae1f`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/sglang0.5.18-sunrise-tangrt1.2.0:2.2.0-0.1.dev1_g3b94dae1f
```

### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  -e TANG_VISIBLE_DEVICES=all \
  $IMG bash
```

Start the app with its default settings:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  -e TANG_VISIBLE_DEVICES=all \
  $IMG
```

Pass arguments to the launcher:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  -e TANG_VISIBLE_DEVICES=all \
  $IMG sglang-serve --model-path <path> --port 9000
```

## Changelog

### 2.2.0-0.1.dev1_g3b94dae1f

*2026-09-28 16:49:04*

Rebuild on a rebuilt sunrise runtime. The FlagTree sunrise wheel was faulty (missing sunriseTritonPlugin.so, so flag_gems could not import triton) and has been re-uploaded; runtime v2 :2.2.0 and v1 :2.2.0-build were rebuilt on it (digests 38eec/8b6fc). This app image was built on the broken runtime and is redone on the fixed one. Same plugin and app pins as the image it replaces.

### 2.1.2-0.1.dev1_g3b94dae1f

*2026-09-11 07:48:15*

sglang 0.5.18 on sunrise TANGRT 1.2.0. First image for this backend: the plugin gains a vendor layer for a platform whose torch is a +cpu build carrying the PTPU device, so the core never short-circuits to its CUDA paths and reaches two fallbacks that only a non-CUDA-alias platform can hit (the device string and the pccl distributed backend). Two flag_gems operators are blacklisted in the app env because the vendor override does not implement them compatibly here: the SDPA math kernel rejects enable_gqa (breaks every GQA model at the first prefill) and the pow fallback fails on scalar**tensor — both are accepted indefinitely, so they are part of the delivered configuration rather than pending follow-ups. The runtime additionally moves to flag_gems 5.3.6 for the asin fallback and the sunrise cumsum guard. F/T dual-compiler serve verified on Qwen3-4B.
