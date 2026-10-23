# SGLang packaging — design

Status: **implemented.** The `docs/` tree is the operator-facing companion (per-version
verification reports, backends records, playbook); this file is the design of record — why,
not what. The `+flagos` repack rules are data in `config.yaml`; the build scripts and
workflows are the live code.

Goal: ship sglang as app images — the runtime image plus a **single-step `pip install`** of a
per-vendor wheel — without disturbing the runtime's torch/triton matrix or pulling a
per-platform `sgl-kernel`.

## Context

sglang's native wheels come in CUDA and non-CUDA variants. The CUDA variant declares
`torch==2.13.0` and `sglang-kernel`; installing it into a FlagOS runtime would overwrite the
carefully-matched torch/triton matrix and force in a per-platform-ABI `sgl-kernel`. So the line
builds from the **non-CUDA variant (`srt_empty` base)**: its `pyproject_other.toml` carries six
deps, none of them torch or sglang-kernel, and `merge-runtime-base.py` folds the 40-item
`runtime_base` into `dependencies` — the wheel's METADATA is **torch-free and
sglang-kernel-free by construction**. Repack then only stamps the `+flagos` local version and
downgrades Metadata-Version (2.4 → 2.2, a Nexus requirement): every rule in `config.yaml` is
empty.

Hardware operators come from the runtime's built-in flag_gems (the zero-sgl-kernel route); the
178-file `sgl_kernel` import surface is satisfied by a shared `sgl-kernel-shim` wheel whose
symbols are never actually called.

### Decisions taken

| Question | Decision |
|---|---|
| Wheel model | **Repack of a self-built sdist**, unlike megatron's fork-source. sglang ships no sdist (wheel-only on PyPI, no GitHub release assets), so `build-sdist.sh` builds one; the `srt_empty` non-CUDA base makes the wheel torch-free/sgl-kernel-free by construction, so no dependency stripping is needed |
| Version | `0.5.18+flagos` — a PEP 440 local suffix that both marks "from the FlagOS repack flow" and lets `pip install sglang==0.5.18+flagos` pin to our wheel instead of drifting to the official `0.5.18` (same as the vllm line) |
| Build environment | **Each backend's runtime image** (`flagos-runtime-<vendor>-<backend>:<version>`), building from the same sdist. ascend aarch64 compiles in the aarch64 container and so produces an aarch64 wheel with no special-casing |
| Zero sgl-kernel | The install chain carries no native `sgl-kernel` wheel: a shared `sgl-kernel-shim` (distribution `sgl-kernel-shim`, version = sglang version, module `sgl_kernel`) satisfies the import surface; hardware operators are all flag_gems. Its source lives in the sglang-plugin-FL repo (`addon/sgl-kernel-shim`), not build-infra |
| Per-vendor patches | `srt_empty` is shared by all backends; per-vendor library differences (e.g. metax's JIT-gap fallbacks) go into build-time patches applied **host-side before the container starts** (`wheels/<vendor>/patches/*.patch`) or into the plugin layer, never into the wheel itself |
| torch compatibility | The repack removes the pip blocker (`torch==2.13.0`); whether each backend's runtime torch (2.8–2.11) actually runs is a per-backend verify-matrix gate, not something the build can prove |
| compressed-tensors | metax serve hard-depends on compressed-tensors (the CUDA-alias quantization chain imports it unconditionally), but the official package declares torch and would clobber the vendor torch in a single-step install. It rides `deps_app` as a **`+flagos` repack** (`0.17.0+flagos`, torch-free `Requires-Dist`), filled per-backend in `configs.yaml` |
| rust toolchain | sglang's rust workspace needs cargo≥1.84 / rustc≥1.85 (edition 2024); Ubuntu 24.04 apt ships 1.75. The build consumes a filestore-cached official dist tarball (`rust-<ver>-<triple>.tar.xz`, default 1.98.0, both x86_64 and aarch64), rustup as fallback |
| Publication | Per-vendor wheel → `flagos-pypi-<vendor>` (upload is opt-in); the sdist goes to the filestore. Audit job runs `audit-deps.py` on the repacked wheel |
| Verification | `verify-sglang-backend.sh` on the backend's node: F/T dual-path E2E; status in `status_matrix.sglang0.5.18.yaml` → `docs/sglang-verification-matrix.md` |

## Not here

- The sglang source and the plugin-layer vendor patches — both live in sglang /
  sglang-plugin-FL. build-infra clones the upstream sdist and overlays only the
  host-side patches in `wheels/<vendor>/patches/`.
- The sgl-kernel-shim source — moved to sglang-plugin-FL `addon/sgl-kernel-shim`
  (2026-09-03); build-infra only consumes it in the shim job.

## See also

- `packaging/sglang/docs/README.md` — the entry point; 结论速览.
- `packaging/sglang/docs/sglang-0.5.18/index.md` — the E2E verification report + backend index.
- `packaging/sglang/docs/sglang-0.5.18/decisions.md` — the ADR record (§5.1–§5.8).
- `packaging/sglang/config.yaml` — the (empty) repack rules, as data.
- `packaging/sglang/build-sdist.sh` / `build-and-repack.sh` / `merge-runtime-base.py` — the build.
- Docs site: Design → SGLang (operator summary, links back here).
