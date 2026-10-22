# vllm-plugin-FL native wheel — design

Status: **implemented.** Six backends ship a native `vllm_fl._C` wheel; the rest stay
pure-Python. The operator-facing companion (what each wheel is, how the label maps to a
backend) lives on the docs site under **Design → vllm-plugin-FL**; this file is the design
of record — why, not what.

Goal: ship the plugin's native `weak_ref_tensor` op to every backend whose torch dispatches
tensors on the CUDA key, so vLLM cudagraph capture holds a genuinely weak reference and does
not leak VRAM per captured graph.

## Context

The pure-Python wheel carries no `vllm_fl._C`, so `vllm_fl/ops/_C_ops_registry.py` falls back
to `("weak_ref_tensor", lambda t: t)` — a **strong** reference. vLLM cudagraph capture needs a
native `torch::from_blob` weak reference to stop `GraphEntry.output` from pinning the previous
graph's pool; with the identity fallback, VRAM grows per captured graph until OOM
(flagos-ai/build-infra#1428 hygon, #1431 MetaX).

The native op is host-side only (`csrc/cuda/weak_ref_tensor.cpp` + `torch_bindings.cpp`,
registered on `c10::kCUDA` via `TORCH_LIBRARY_EXPAND`) — no device kernels, no arch. `_patch_custom_ops`
already `import vllm_fl._C` before installing the fallback, so a wheel that carries the `.so`
never installs the identity.

### Decisions taken

| Question | Decision |
|---|---|
| Who needs `_C` | Backends whose torch dispatches tensors on the CUDA key (`tensor.is_cuda()` true): real CUDA, HIP, and MACA/CUDA-alias torch. That is **nvidia×2, metax×2, hygon, kunlunxin**. The plugin's own `is_cuda_alike()` is NOT the discriminator — it returns `False` for hygon, which empirically needed `_C` |
| Builder image | **None.** The wheel builds in-place inside each backend's **runtime** image (`flagos-runtime-<vendor>-<backend>:<version>`) via a `bash -c` block in `vllm-plugin-wheel.yml` — no per-vendor Containerfile |
| Why no Containerfile | Build env must equal delivery env: the `.so` links the exact torch/ABI/glibc the app image runs against, so the build runs *inside* that backend's runtime image rather than a separate toolchain image that could drift |
| Per-backend variation | `packaging/vllm/plugin-build.yaml` knobs, not Dockerfiles: `cmake_args` (hygon), `metax_mxcc` / `gpp_direct` (g++-direct recipes), `wire_cuda_repo` + `cuda_nvcc` + `cuda_extra_apt` (nvidia), `torch_prefix` (g++ rows), `librt_symlink` |
| Build path split | nvidia/hygon take the cmake + `find_package(Torch)` path (nvidia needs `cuda-nvcc` via apt because TorchConfig FATALs without it); metax/kunlunxin take a plain-`g++` compile of the two host-side TUs — their torch ships no nvcc and `find_package(Torch)` dies at `enable_language(CUDA)` |
| Label scheme | Native wheels carry a local label = the **bare backend name** with `-`→`.` (`+maca3.7.2.1`, `+cuda12.8`, `+dtk26.4`, `+xre5.37.1`). No vendor prefix — the wheel already lands on a per-vendor index, so the vendor would be carried twice |
| App-side pin | Derived mechanically: `vllm-app-image.yml` takes only the public version in `plugin_fl_version` and appends `+<bare-backend>` for native backends (tag form `+`, temp form extends the existing `+g<sha>.d<date>` with `.`). The installed-vs-requested gate compares against the PEP 440-normalized pin |
| Wheel tag | Native wheels fold to honest `cp3xx-linux_x86_64` (derived from the `.so`'s EXT_SUFFIX); pure wheels stay `py3-none-any` |
| Recording | The publish steps leave a TSV manifest per lane; `record-wheel-info.yml` merges it into `packaging/packages.yaml` and opens a review-gated PR. The pure and native lanes pass disjoint `manifest_pattern` globs so one record job never cross-downloads the other's manifests |

## Not here

- metax `mcoplib` (fused kernels) — separate follow-up, blocked on a `maca3.8.1`/`torch2.10`
  mcoplib wheel existing on `flagos-pypi-metax`.
- A plugin-side fail-safe guard (force `cudagraph_mode=NONE` when no real weak-ref provider
  exists) — upstream vllm-plugin-FL change, not this repo.

## See also

- `packaging/vllm/plugin-build.yaml` — the per-backend field contract and rationale.
- `.github/workflows/vllm-plugin-wheel.yml` — `build-native` job (the `bash -c` build block).
- Docs site: Design → vllm-plugin-FL (operator summary, links back here).
