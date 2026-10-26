---
title: vllm-plugin-FL
weight: 10
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


vllm-plugin-FL is installed into every vLLM app image as a prebuilt wheel from
the vendor PyPI. Most backends get a pure-Python wheel; a few get a **native**
wheel that also carries a compiled `vllm_fl._C` extension.

## What the native extension is for

`vllm_fl._C` provides the plugin's `weak_ref_tensor` op. vLLM cudagraph capture
needs a genuinely weak reference to a captured tensor; when the extension is
missing, the plugin falls back to an identity that holds a **strong** reference,
and vRAM leaks per captured graph until the server OOMs during capture.

## Who gets the native wheel

The extension registers on CUDA, so it only helps backends whose torch actually
dispatches tensors on the CUDA key. That is six backends:

- `nvidia-cuda12.8`, `nvidia-cuda13.3`
- `metax-maca3.7.2.1`, `metax-maca3.8.1.3`
- `hygon-dtk26.04`
- `kunlunxin-xre5.37.1`

Every other backend (ascend, cambricon, enflame, mthreads, sunrise, tsingmicro,
iluvatar, …) uses a pure-Python wheel.

## Why there is no builder image

Unlike FlagTree or FlagCX, the native wheel has no Containerfile of its own. It
is built **inside each backend's runtime image** (`flagos-runtime-<vendor>-<backend>`),
because the compiled extension must link the exact torch/ABI/glibc the app image
will run against — the build environment has to equal the delivery environment.
A separate toolchain image could drift from what is actually shipped.

## Wheel labels

Native wheels carry a local version label equal to the bare backend name (with
`-` folded to `.`):

| Backend | Wheel |
|---|---|
| `nvidia-cuda12.8` | `0.3.0+cuda12.8` |
| `nvidia-cuda13.3` | `0.3.0+cuda13.3` |
| `metax-maca3.7.2.1` | `0.3.0+maca3.7.2.1` |
| `metax-maca3.8.1.3` | `0.3.0+maca3.8.1.3` |
| `hygon-dtk26.04` | `0.3.0+dtk26.4` |
| `kunlunxin-xre5.37.1` | `0.3.0+xre5.37.1` |

There is no vendor prefix — the wheel already lands on a per-vendor index
(`flagos-pypi-<vendor>`), so the vendor would be carried twice. The app build
derives the full pin from the backend name, so a dispatch only ever names the
public version (`0.3.0`).

The label reaches the pin, never the image tag: one index carries several
native builds under one public version (`flagos-pypi-nvidia` holds `0.3.0`,
`0.3.0+cuda12.8` and `0.3.0+cuda13.3`), and a bare `==0.3.0` resolves to the
newest local version — another backend's `.so` — so **the installed pin must
carry the label**. The app tag's plugin segment stays at the public version:
the repository segment already names the backend, and a label there breaks the
two consumers that parse the tag's suffix (the verify driver's pin recovery and
the record step's plugin-commit drift gate).

## Full rationale

The design of record lives beside the code:

- [packaging/vllm/DESIGN.md](https://github.com/flagos-ai/build-infra/blob/main/packaging/vllm/DESIGN.md) — the decisions, in a maintainer-facing form.
- [packaging/vllm/plugin-build.yaml](https://github.com/flagos-ai/build-infra/blob/main/packaging/vllm/plugin-build.yaml) — the per-backend build knobs and their rationale.
