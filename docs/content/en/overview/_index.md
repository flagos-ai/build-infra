---
title: Overview
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


FlagOS images are layered. Each layer builds on the one below it and has a
distinct concern.

## base

A vendor's SDK/toolkit installed on an OS base. A base image is **only** about:

- the **base operating system** (the containerfile's `FROM`),
- the **supported SDK version** (the backend name, e.g. `cuda12.8`, `cann9.0.0`),
- and the **contents** installed on top (system packages + vendor SDK packages).

It has **nothing to do** with Python, Torch, or Triton versions — those are a
runtime concern. Built from `base/<vendor>-<backend>` by `base/build.py`, tagged
`flagos-base-<vendor>-<backend>:<version>-<revision>`.

## runtime

Built on a base image; adds the **Python interpreter** and the **software stack**
(Torch, Triton, FlagTree, FlagGems). Built by `runtime/build.py`, image
`flagos-runtime-<vendor>-<backend>`.

## application (future)

Built on a runtime image; packages a ready-to-run application (vLLM, Megatron-LM,
SGLang, …).

## Registry & source of truth

All images go to a single registry configured in `.github/build-config.yml`,
differing only by a path prefix per layer. `configs.yaml` holds each backend's
dependencies and environment; the `base/<name>` containerfiles carry the OS + SDK.
The catalogs and per-image pages here are generated from those files.
